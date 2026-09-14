"""
Script worker — breaks down the video plan into detailed scene shots.

Stage 3: Takes the AI plan and creates a detailed shot list with
exact timing, camera movements, and narration per shot.
"""
import json
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker


class ScriptWorker(BaseWorker):
    stage_name = "script_breakdown"

    def run(self) -> Dict[str, Any]:
        plan = self._load_plan()
        if not plan:
            return {"status": "error", "error": "No plan found"}

        breakdown = self._break_down(plan)
        path = self._save_breakdown(breakdown)
        return {
            "status": "success",
            "breakdown_path": path,
            "total_shots": len(breakdown.get("shots", [])),
            "total_scenes": len(breakdown.get("scenes", [])),
        }

    def _load_plan(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        plan_path = os.path.join(artifact_dir, "video_plan.json")
        if not os.path.exists(plan_path):
            self.logger.error(f"Plan file not found: {plan_path}")
            return {}
        with open(plan_path) as f:
            return json.load(f)

    def _break_down(self, plan: Dict) -> Dict[str, Any]:
        fps = plan.get("fps", 24)
        scenes = plan.get("scenes", [])
        shots = []

        for scene in scenes:
            duration = scene.get("duration_sec", 15)
            frame_count = int(duration * fps)
            shot = {
                "scene_id": scene["id"],
                "scene_name": scene["name"],
                "description": scene.get("description", ""),
                "duration_sec": duration,
                "frame_start": sum(s.get("duration_sec", 15) for s in scenes[:scene["id"]-1]) * fps + 1,
                "frame_end": 0,  # set below
                "fps": fps,
                "camera": scene.get("camera", {}),
                "characters": scene.get("characters", []),
                "environment": scene.get("environment", {}),
                "props": scene.get("props", []),
                "narration": scene.get("narration", ""),
            }
            shot["frame_end"] = shot["frame_start"] + frame_count - 1
            shots.append(shot)

        total_frames = sum(s["frame_end"] - s["frame_start"] + 1 for s in shots)
        return {
            "title": plan.get("title", "Untitled"),
            "fps": fps,
            "total_frames": total_frames,
            "total_duration_sec": total_frames / fps,
            "scenes": scenes,
            "shots": shots,
            "render_config": {
                "engine": plan.get("render_engine", "BLENDER_EEVEE"),
                "resolution": plan.get("resolution", [1280, 720]),
                "samples": plan.get("samples", 64),
            },
        }

    def _save_breakdown(self, breakdown: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "script_breakdown.json")
        with open(path, "w") as f:
            json.dump(breakdown, f, indent=2)
        self.logger.info(f"Script breakdown saved: {path}")
        return path
