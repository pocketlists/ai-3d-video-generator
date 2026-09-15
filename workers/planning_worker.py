"""
Planning worker — uses LLM provider (Gemini/OpenAI/template) for AI planning.

Stage 2: AI generates the video production plan.
This worker now uses the provider abstraction layer.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from providers.llm_provider import get_llm_provider, LLMError


class PlanningWorker(BaseWorker):
    stage_name = "ai_planning"

    def run(self) -> Dict[str, Any]:
        prompt = self.config.get("prompt", "A serene low-poly landscape at sunrise")
        self.logger.info(f"Planning video for prompt: {prompt[:80]}")

        llm = get_llm_provider(self.config)
        self.logger.info(f"Using LLM provider: {llm.__class__.__name__}")

        try:
            plan = llm.generate_plan(prompt)
        except LLMError as e:
            self.logger.error(f"LLM planning failed: {e}")
            # Use template fallback
            from providers.llm_provider import TemplateProvider
            plan = TemplateProvider(self.config).generate_plan(prompt)
            plan["fallback_used"] = True
            plan["fallback_reason"] = str(e)

        plan_path = self._save_plan(plan)
        return {
            "status": "success",
            "prompt": prompt,
            "plan_path": plan_path,
            "scene_count": len(plan.get("scenes", [])),
            "provider": plan.get("provider", "unknown"),
            "ai_generated": plan.get("ai_generated", False),
        }

    def _save_plan(self, plan: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "video_plan.json")
        with open(path, "w") as f:
            json.dump(plan, f, indent=2)
        self.logger.info(f"Plan saved to: {path}")
        return path
