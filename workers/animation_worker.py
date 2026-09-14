"""Animation worker — generates animation keyframes and motion data.

Stage 8: Creates keyframe animation data for characters, objects,
and camera movements based on the script breakdown.
"""
import json
import math
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker


class AnimationWorker(BaseWorker):
    stage_name = "animation"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        animations = self._generate_animations(breakdown)
        path = self._save_animations(animations)
        return {
            "status": "success",
            "animations_path": path,
            "shot_count": len(animations.get("shots", [])),
            "total_keyframes": animations.get("total_keyframes", 0),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_animations(self, breakdown: Dict) -> Dict[str, Any]:
        fps = breakdown.get("fps", 24)
        shots = breakdown.get("shots", [])
        anim_shots = []
        total_keyframes = 0

        for shot in shots:
            frame_start = shot["frame_start"]
            frame_end = shot["frame_end"]
            keyframes = []

            # Character walk animation (simple bob)
            for char in shot.get("characters", []):
                pos = char.get("position", [0, 0, 0])
                for frame in range(frame_start, frame_end + 1, fps):  # keyframe every second
                    progress = (frame - frame_start) / max(frame_end - frame_start, 1)
                    x = pos[0] + progress * 2  # walk forward
                    bob = math.sin((frame - frame_start) * 0.3) * 0.05
                    keyframes.append({
                        "frame": frame,
                        "object": char["name"],
                        "location": [x, pos[1], pos[2] + bob],
                        "rotation": [0, 0, 0],
                    })
                    total_keyframes += 1

            # Prop animation (gentle rotation)
            for prop in shot.get("props", []):
                pos = prop.get("position", [0, 0, 0])
                for frame in range(frame_start, frame_end + 1, fps * 2):
                    keyframes.append({
                        "frame": frame,
                        "object": prop["name"],
                        "location": pos,
                        "rotation": [0, 0, (frame - frame_start) * 0.05],
                    })
                    total_keyframes += 1

            anim_shots.append({
                "scene_id": shot["scene_id"],
                "frame_start": frame_start,
                "frame_end": frame_end,
                "keyframes": keyframes,
            })

        return {
            "fps": fps,
            "shots": anim_shots,
            "total_keyframes": total_keyframes,
        }

    def _save_animations(self, animations: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "animations.json")
        with open(path, "w") as f:
            json.dump(animations, f, indent=2)
        return path
