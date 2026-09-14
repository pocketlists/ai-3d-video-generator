"""
Camera worker — generates camera paths and keyframes.

Stage 9: Creates camera movement data (static, orbit, dolly, pan)
for each shot based on the script breakdown.
"""
import json
import math
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker


class CameraWorker(BaseWorker):
    stage_name = "camera"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        camera_data = self._generate_camera_paths(breakdown)
        path = self._save_camera_data(camera_data)
        return {
            "status": "success",
            "camera_path": path,
            "shot_count": len(camera_data.get("shots", [])),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_camera_paths(self, breakdown: Dict) -> Dict[str, Any]:
        shots = breakdown.get("shots", [])
        cam_shots = []

        for shot in shots:
            cam = shot.get("camera", {})
            cam_type = cam.get("type", "static")
            loc = cam.get("location", [5, -5, 3])
            target = cam.get("target", [0, 0, 1])
            frame_start = shot["frame_start"]
            frame_end = shot["frame_end"]

            keyframes = []

            if cam_type == "static":
                keyframes = [
                    {"frame": frame_start, "location": loc, "target": target},
                    {"frame": frame_end, "location": loc, "target": target},
                ]
            elif cam_type == "orbit":
                # Orbit around target
                radius = math.sqrt(sum((a - b) ** 2 for a, b in zip(loc, target)))
                for frame in range(frame_start, frame_end + 1, max(1, (frame_end - frame_start) // 8)):
                    angle = (frame - frame_start) / max(frame_end - frame_start, 1) * 2 * math.pi
                    x = target[0] + radius * math.cos(angle)
                    y = target[1] + radius * math.sin(angle)
                    z = loc[2]
                    keyframes.append({"frame": frame, "location": [x, y, z], "target": target})
            elif cam_type == "dolly":
                # Move camera forward
                for frame in range(frame_start, frame_end + 1, max(1, (frame_end - frame_start) // 4)):
                    progress = (frame - frame_start) / max(frame_end - frame_start, 1)
                    x = loc[0] * (1 - progress * 0.3)
                    y = loc[1] * (1 - progress * 0.3)
                    z = loc[2]
                    keyframes.append({"frame": frame, "location": [x, y, z], "target": target})

            cam_shots.append({
                "scene_id": shot["scene_id"],
                "cam_type": cam_type,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "keyframes": keyframes,
            })

        return {"shots": cam_shots}

    def _save_camera_data(self, data: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "camera_data.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
