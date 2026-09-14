"""
Planning worker — receives requests and creates AI-driven video plans.

Stage 1 (receive_request): Intake from Telegram
Stage 2 (ai_planning): AI generates storyboard, scene plan, and asset list.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

from workers.base_worker import BaseWorker


class PlanningWorker(BaseWorker):
    stage_name = "ai_planning"

    def run(self) -> Dict[str, Any]:
        prompt = self.config.get("prompt", "A serene low-poly landscape at sunrise")
        self.logger.info(f"Planning video for prompt: {prompt}")

        plan = self._generate_plan(prompt)
        plan_path = self._save_plan(plan)
        return {
            "status": "success",
            "prompt": prompt,
            "plan_path": plan_path,
            "scene_count": len(plan.get("scenes", [])),
            "estimated_duration_sec": plan.get("estimated_duration", 60),
        }

    def _generate_plan(self, prompt: str) -> Dict[str, Any]:
        """Generate a video plan. Uses AI API if available, else template."""
        api_key = self.config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")

        if api_key:
            self.logger.info("Using AI API for planning")
            plan = self._plan_with_ai(prompt, api_key)
        else:
            self.logger.info("No AI API key found, using template-based planning")
            plan = self._plan_template(prompt)

        return plan

    def _plan_with_ai(self, prompt: str, api_key: str) -> Dict[str, Any]:
        """Generate plan using AI (OpenAI-compatible API)."""
        import urllib.request
        import urllib.error

        system_msg = (
            "You are a 3D video director. Create a JSON plan for a 1-minute "
            "low-poly 3D video. Include scenes, characters, environments, props, "
            "camera movements, and narration. Keep it suitable for CPU rendering."
        )

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            # Try to parse JSON from response
            if "{" in content:
                start = content.index("{")
                end = content.rindex("}") + 2
                plan = json.loads(content[start:end])
            else:
                plan = self._plan_template(prompt)
            plan["ai_generated"] = True
            return plan
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            self.logger.warning(f"AI planning failed: {e}, falling back to template")
            return self._plan_template(prompt)

    def _plan_template(self, prompt: str) -> Dict[str, Any]:
        """Generate a template-based plan when no AI API is available."""
        return {
            "title": f"Low-poly video: {prompt[:50]}",
            "prompt": prompt,
            "ai_generated": False,
            "estimated_duration": 60,
            "fps": 24,
            "total_frames": 1440,
            "scenes": [
                {
                    "id": 1,
                    "name": "opening_shot",
                    "duration_sec": 15,
                    "description": f"Wide establishing shot of {prompt}",
                    "camera": {"type": "static", "location": [8, -8, 4], "target": [0, 0, 1]},
                    "characters": [],
                    "environment": {"type": "outdoor", "features": ["trees", "ground"]},
                    "props": [],
                    "narration": "A beautiful low-poly scene unfolds.",
                },
                {
                    "id": 2,
                    "name": "main_action",
                    "duration_sec": 30,
                    "description": "Main action with characters",
                    "camera": {"type": "orbit", "location": [5, -5, 3], "target": [0, 0, 1]},
                    "characters": [{"name": "hero", "position": [0, 0, 0]}],
                    "environment": {"type": "outdoor"},
                    "props": [{"name": "crate", "type": "box", "position": [1, 1, 0]}],
                    "narration": "The hero explores the landscape.",
                },
                {
                    "id": 3,
                    "name": "closing_shot",
                    "duration_sec": 15,
                    "description": "Closing wide shot",
                    "camera": {"type": "static", "location": [10, -10, 5], "target": [0, 0, 1]},
                    "characters": [],
                    "environment": {"type": "outdoor"},
                    "props": [],
                    "narration": "The scene fades to a close.",
                },
            ],
            "assets_required": {
                "characters": ["hero"],
                "environments": ["outdoor"],
                "props": ["crate"],
                "audio": {"voice": True, "music": True, "sfx": True},
            },
        }

    def _save_plan(self, plan: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "video_plan.json")
        with open(path, "w") as f:
            json.dump(plan, f, indent=2)
        self.logger.info(f"Plan saved to: {path}")
        return path
