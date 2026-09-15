"""
Hermes Agent — orchestration layer (NOT heavy rendering).

Architecture:
Telegram → Hermes → Controller → Workers → Providers/Blender/FFmpeg → Results → Hermes

Hermes decides:
- planning strategy
- asset strategy (which provider)
- provider choice
- retry strategy (via error classifier)
- escalation (via Telegram)
- recovery (resume from checkpoint)
- quality decisions
- optimization decisions

Hermes does NOT bypass the state manager.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from controller.config_loader import ConfigLoader
from controller.state_manager import StateManager
from controller.pipeline import Pipeline
from controller.telegram_escalation import TelegramEscalation
from controller.checkpoint import CheckpointManager, Checkpoint
from core.storage import get_state_store
from utils.logger import PipelineLogger
from utils.telemetry import TelemetryCollector
from utils.error_classifier import classify_error, should_retry, should_escalate, get_retry_delay

from providers.llm_provider import get_llm_provider, LLMError, LLMProvider
from providers.tts_provider import get_tts_provider
from providers.asset_router import AssetRouter
from providers.audio_provider import get_music_provider, get_sfx_provider
from providers.lip_sync_provider import get_lip_sync_provider


class HermesAgent:
    """Central agent that orchestrates the video generation pipeline."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.config
        self.pipeline = Pipeline()
        self.state = StateManager()
        self.checkpoint = CheckpointManager(self.state.job_id or "default")
        self.logger = PipelineLogger("hermes")
        self.telemetry = TelemetryCollector()
        self.escalation = TelegramEscalation(self.config)

        # Initialize providers (may raise LLMError if configured provider unavailable)
        try:
            self.llm = get_llm_provider(self.config)
        except LLMError as e:
            self.logger.error(f"LLM provider init failed: {e}")
            self.llm = None
            self._llm_error = str(e)
        else:
            self._llm_error = None

        self.tts = get_tts_provider(self.config)
        self.asset_router = AssetRouter(self.config)
        self.music = get_music_provider(self.config)
        self.sfx = get_sfx_provider(self.config)
        self.lip_sync = get_lip_sync_provider(self.config)

        self.job_id: Optional[str] = None
        self.logger.info("Hermes Agent initialized (v3.0)")

    def receive_request(self, prompt: str, style: str = "low-poly") -> str:
        """Receive a video generation request. Returns job_id."""
        self.job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.state.job_id = self.job_id
        self.state.transition("PLANNING")
        self.state.set_stage_status("receive_request", "completed", {
            "job_id": self.job_id, "prompt": prompt, "style": style,
        })
        self.logger.info(f"Request received: {self.job_id} — {prompt[:80]} (style: {style})")
        self.escalation.send_progress(self.job_id, "receive_request", "Request received")
        return self.job_id

    def plan_production(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        """Create production plan via LLM provider. Escalates on failure — no silent fallback."""
        if not self.llm:
            return self._escalate("ai_planning", self._llm_error or "LLM provider unavailable", "gemini")

        self.state.set_stage_status("ai_planning", "PLANNING")
        self.logger.info(f"Planning production for: {prompt[:80]} (style: {style})")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                plan = self.llm.generate_plan(prompt, style)
                self.state.mark_completed("ai_planning", {"plan": plan})
                self.logger.info(f"Plan created via {plan.get('provider', 'unknown')}")
                self.escalation.send_progress(self.job_id, "ai_planning", "Planning complete")
                return plan
            except LLMError as e:
                error_type = classify_error(str(e))
                self.logger.warning(f"Planning attempt {attempt} failed ({error_type}): {e}")

                if should_retry(error_type, attempt, max_attempts):
                    delay = get_retry_delay(error_type, attempt)
                    self.logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    continue

                # Exhausted retries — escalate
                if should_escalate(error_type, attempts_exhausted=True):
                    return self._escalate("ai_planning", str(e),
                                          self.llm.__class__.__name__)
                # Non-retryable, non-escalatable — fail
                self.state.mark_failed("ai_planning", str(e), recoverable=False)
                return {"status": "failed", "stage": "ai_planning", "error": str(e)}

        return self._escalate("ai_planning", "Max retries exceeded", "gemini")

    def _escalate(self, stage: str, error: str, provider: str) -> Dict[str, Any]:
        """Escalate failure to Telegram — set WAITING and signal runner exit."""
        self.logger.warning(f"Escalating {stage} failure: {error}")
        escalation_info = self.escalation.escalate_failure(
            self.job_id or "unknown", stage, error, provider,
        )

        # Mark state as waiting
        self.state.mark_waiting(stage, error,
                                resume_token=escalation_info.get("resume_token", ""),
                                message_id=escalation_info.get("message_id"))

        return {
            "status": "WAITING_FOR_EXTERNAL_RESPONSE",
            "stage": stage,
            "error": error,
            "provider": provider,
            **escalation_info,
        }

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
        self.logger.info(f"Running stage: {stage_name}")
        self.escalation.send_progress(self.job_id, stage_name, "Running")
        start = time.time()

        try:
            result = self._execute_stage(stage_name)
            elapsed = time.time() - start
            self.state.mark_completed(stage_name, {"elapsed": elapsed, "result": result})
            self.state.record_metric(f"{stage_name}_elapsed", round(elapsed, 2))
            self.logger.info(f"Stage '{stage_name}' completed in {elapsed:.1f}s")
            self.escalation.send_progress(self.job_id, stage_name, "Completed")
            return True
        except Exception as e:
            elapsed = time.time() - start
            self.logger.error(f"Stage '{stage_name}' failed: {e}")
            self.state.mark_failed(stage_name, str(e), recoverable=True)

            error_type = classify_error(str(e))
            if should_escalate(error_type, attempts_exhausted=True):
                self._escalate(stage_name, str(e), "worker")
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

    def run_pipeline(self, prompt: str, style: str = "low-poly") -> bool:
        """Run the entire pipeline with Hermes oversight."""
        self.logger.info(f"Starting pipeline: {prompt[:80]} (style: {style})")
        self.receive_request(prompt, style)

        plan = self.plan_production(prompt, style)
        if plan.get("status") == "WAITING_FOR_EXTERNAL_RESPONSE":
            self.logger.warning("Pipeline paused — waiting for external response")
            return False
        if plan.get("status") == "failed":
            self.logger.error("Planning failed completely")
            return False

        layers = self.pipeline.get_execution_order()
        for i, layer in enumerate(layers):
            self.logger.info(f"Layer {i+1}: {', '.join(layer)}")
            for stage_name in layer:
                if stage_name in ("receive_request", "ai_planning"):
                    continue
                success = self.run_stage(stage_name)
                if not success:
                    self.logger.error(f"Pipeline halted at: {stage_name}")
                    self.escalation.send_error(self.job_id, stage_name, "Pipeline halted")
                    return False

        self.logger.info("Pipeline completed successfully!")
        self.escalation.send_progress(self.job_id, "completed", "Pipeline complete!")
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.get_full_state(),
            "llm_provider": self.llm.__class__.__name__ if self.llm else None,
            "llm_error": self._llm_error,
            "escalations": self.state.get_pending_escalations(),
        }
