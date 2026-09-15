"""
Hermes Agent — central orchestration layer for the entire pipeline.

Hermes coordinates tools, APIs, workers, retries, human/AI escalation,
state, and decisions. It is NOT the LLM itself — it uses LLM providers.

Responsibilities:
- Receive video generation requests
- Create structured production plans via LLM providers
- Coordinate all pipeline stages
- Handle failures with retry + Telegram escalation
- Support WAITING_FOR_EXTERNAL_RESPONSE state
- Resume from failed stage after external response
- Report progress to Telegram
- Deliver final output
"""
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from controller.config_loader import ConfigLoader
from controller.state_manager import StateManager
from controller.pipeline import Pipeline
from controller.telegram_escalation import TelegramEscalation
from utils.logger import PipelineLogger
from utils.telemetry import TelemetryCollector

from providers.llm_provider import get_llm_provider, LLMError
from providers.tts_provider import get_tts_provider
from providers.asset_provider import get_asset_provider
from providers.audio_provider import get_music_provider, get_sfx_provider
from providers.lip_sync_provider import get_lip_sync_provider


class HermesAgent:
    """Central agent that orchestrates the entire video generation pipeline."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.config
        self.pipeline = Pipeline()
        self.state = StateManager()
        self.logger = PipelineLogger("hermes")
        self.telemetry = TelemetryCollector()
        self.escalation = TelegramEscalation(self.config)

        # Initialize providers
        self.llm = get_llm_provider(self.config)
        self.tts = get_tts_provider(self.config)
        self.asset_provider = get_asset_provider(self.config)
        self.music = get_music_provider(self.config)
        self.sfx = get_sfx_provider(self.config)
        self.lip_sync = get_lip_sync_provider(self.config)

        self.job_id: Optional[str] = None
        self.logger.info("Hermes Agent initialized")

    def receive_request(self, prompt: str) -> str:
        """Receive a video generation request. Returns job_id."""
        self.job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        self.state.set_stage_status("receive_request", "completed", {
            "job_id": self.job_id, "prompt": prompt
        })
        self.logger.info(f"Request received: {self.job_id} — {prompt[:80]}")
        self.escalation.send_progress(self.job_id, "receive_request", "Request received")
        return self.job_id

    def plan_production(self, prompt: str) -> Dict[str, Any]:
        """Create a structured production plan using LLM provider."""
        self.state.set_stage_status("ai_planning", "running")
        self.logger.info(f"Planning production for: {prompt[:80]}")

        try:
            plan = self.llm.generate_plan(prompt)
            self.state.set_stage_status("ai_planning", "completed", {"plan": plan})
            self.logger.info(f"Plan created via {plan.get('provider', 'unknown')}")
            self.escalation.send_progress(self.job_id, "ai_planning", "Planning complete")
            return plan
        except LLMError as e:
            self.logger.error(f"LLM planning failed: {e}")
            self.state.record_error("ai_planning", str(e), recoverable=True)
            # Attempt Telegram escalation
            return self._handle_stage_failure("ai_planning", str(e), prompt)
        except Exception as e:
            self.logger.error(f"Planning error: {e}")
            return self._handle_stage_failure("ai_planning", str(e), prompt)

    def run_stage(self, stage_name: str) -> bool:
        """Run a single pipeline stage with Hermes oversight."""
        stage = self.pipeline.get_stage(stage_name)
        if not stage:
            self.logger.error(f"Unknown stage: {stage_name}")
            return False

        # Check dependencies
        for dep in stage.depends_on:
            if not self.state.is_stage_complete(dep):
                self.logger.error(f"Dependency '{dep}' not complete for '{stage_name}'")
                return False

        self.state.set_stage_status(stage_name, "running")
        self.logger.info(f"Running stage: {stage_name} — {stage.description}")
        self.escalation.send_progress(self.job_id, stage_name, "Running")
        start = time.time()

        try:
            result = self._execute_stage(stage_name)
            elapsed = time.time() - start
            self.state.set_stage_status(stage_name, "completed", {
                "elapsed": elapsed, "result": result
            })
            self.state.record_metric(f"{stage_name}_elapsed", round(elapsed, 2))
            self.logger.info(f"Stage '{stage_name}' completed in {elapsed:.1f}s")
            self.escalation.send_progress(self.job_id, stage_name, "Completed")
            return True
        except Exception as e:
            elapsed = time.time() - start
            self.logger.error(f"Stage '{stage_name}' failed: {e}")
            self.state.record_error(stage_name, str(e), recoverable=True)
            self.state.set_stage_status(stage_name, "failed", {"error": str(e)})
            # Attempt escalation
            self._handle_stage_failure(stage_name, str(e), "")
            return False

    def _execute_stage(self, stage_name: str) -> Dict[str, Any]:
        """Execute the actual work for a stage via its worker."""
        from workers import WORKER_REGISTRY
        worker_cls = WORKER_REGISTRY.get(stage_name)
        if not worker_cls:
            raise ValueError(f"No worker registered for stage: {stage_name}")
        worker = worker_cls(self.config, self.state)
        result = worker.run()
        if isinstance(result, dict) and result.get("status") == "error":
            raise Exception(result.get("error", "Worker returned error"))
        return result

    def _handle_stage_failure(self, stage_name: str, error: str, context: str) -> Dict:
        """Handle a stage failure — retry then escalate to Telegram."""
        self.logger.warning(f"Handling failure in {stage_name}: {error}")

        # Check if this is a permanent error
        permanent_keywords = ["authentication", "invalid key", "unauthorized", "forbidden"]
        is_permanent = any(kw in error.lower() for kw in permanent_keywords)

        if is_permanent:
            self.logger.error(f"Permanent error in {stage_name}: {error}")
            self.escalation.send_error(self.job_id, stage_name, error, permanent=True)
            return {"status": "failed", "stage": stage_name, "error": error}

        # Escalate to Telegram — wait for external response
        self.logger.info(f"Escalating to Telegram: {stage_name}")
        self.state.set_stage_status(stage_name, "WAITING_FOR_EXTERNAL_RESPONSE", {
            "error": error, "context": context, "escalated_at": time.time()
        })

        response = self.escalation.escalate_failure(
            self.job_id, stage_name, error, context
        )

        if response:
            self.logger.info(f"External response received for {stage_name}")
            self.state.set_stage_status(stage_name, "completed", {
                "resumed": True, "external_response": response
            })
            return {"status": "resumed", "stage": stage_name, "response": response}
        else:
            # No response — use fallback
            self.logger.warning(f"No external response for {stage_name}, using fallback")
            return self._use_fallback(stage_name, context)

    def _use_fallback(self, stage_name: str, context: str) -> Dict:
        """Use fallback method when primary fails and no external response."""
        from providers.llm_provider import TemplateProvider
        if stage_name == "ai_planning":
            template = TemplateProvider(self.config)
            plan = template.generate_plan(context)
            return plan
        return {"status": "fallback", "stage": stage_name}

    def run_pipeline(self, prompt: str) -> bool:
        """Run the entire pipeline with Hermes oversight."""
        self.logger.info(f"Starting pipeline: {prompt[:80]}")
        self.receive_request(prompt)

        plan = self.plan_production(prompt)
        if not plan:
            self.logger.error("Planning failed completely")
            return False

        layers = self.pipeline.get_execution_order()
        for i, layer in enumerate(layers):
            self.logger.info(f"Layer {i+1}: {', '.join(layer)}")
            for stage_name in layer:
                if stage_name == "receive_request":
                    continue  # Already done
                if stage_name == "ai_planning":
                    continue  # Already done
                success = self.run_stage(stage_name)
                if not success:
                    self.logger.error(f"Pipeline halted at: {stage_name}")
                    self.escalation.send_error(self.job_id, stage_name, "Pipeline halted")
                    return False

        self.logger.info("Pipeline completed successfully!")
        self.escalation.send_progress(self.job_id, "completed", "Pipeline complete!")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "job_id": self.job_id,
            "state": self.state.get_full_state(),
            "providers": {
                "llm": self.llm.__class__.__name__,
                "tts": self.tts.__class__.__name__,
                "asset": self.asset_provider.__class__.__name__,
                "music": self.music.__class__.__name__,
                "sfx": self.sfx.__class__.__name__,
                "lip_sync": self.lip_sync.__class__.__name__,
            },
        }

    def export_state(self) -> str:
        return self.state.export_json()
