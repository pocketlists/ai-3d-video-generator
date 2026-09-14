"""
Lighting worker — sets up lighting rigs and light animation.

Stage 10: Configures key, fill, and rim lights for each scene,
with optional light animation for dynamic effects.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker


class LightingWorker(BaseWorker):
    stage_name = "lighting"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        lighting = self._generate_lighting(breakdown)
        path = self._save_lighting(lighting)
        return {
            "status": "success",
            "lighting_path": path,
            "shot_count": len(lighting.get("shots", [])),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_lighting(self, breakdown: Dict) -> Dict[str, Any]:
        shots = breakdown.get("shots", [])
        light_shots = []

        for shot in shots:
            # Three-point lighting setup
            light_shots.append({
                "scene_id": shot["scene_id"],
                "frame_start": shot["frame_start"],
                "frame_end": shot["frame_end"],
                "lights": [
                    {
                        "name": "key_light",
                        "type": "sun",
                        "energy": 3.0,
                        "location": [5, 5, 10],
                        "rotation": [0.6, 0.3, 0.5],
                        "color": [1.0, 0.95, 0.8],
                    },
                    {
                        "name": "fill_light",
                        "type": "area",
                        "energy": 1.5,
                        "location": [-5, -3, 5],
                        "size": 3.0,
                        "color": [0.8, 0.85, 1.0],
                    },
                    {
                        "name": "rim_light",
                        "type": "sun",
                        "energy": 1.0,
                        "location": [0, -5, 8],
                        "rotation": [-0.5, 0, 0],
                        "color": [1.0, 0.9, 0.7],
                    },
                    {
                        "name": "ambient",
                        "type": "world",
                        "energy": 0.3,
                        "color": [0.5, 0.6, 0.8],
                    },
                ],
            })

        return {"shots": light_shots}

    def _save_lighting(self, data: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "lighting_data.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
