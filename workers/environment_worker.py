"""
Environment worker — generates low-poly environment/scene meshes.

Stage 6: Creates terrain, ground, trees, and other environment elements.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from blender.low_poly_generator import LowPolyGenerator


class EnvironmentWorker(BaseWorker):
    stage_name = "environments"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        generator = LowPolyGenerator(seed=123)
        environments = []
        for env_spec in manifest.get("environments", []):
            mesh = generator.generate_environment(env_spec["name"])
            env_data = {
                "name": env_spec["name"],
                "mesh": mesh.to_dict(),
                "vertex_count": mesh.vertex_count(),
                "face_count": mesh.face_count(),
            }
            environments.append(env_data)
            self.logger.info(f"Generated environment: {env_spec['name']} ({mesh.face_count()} faces)")

        path = self._save_environments(environments)
        return {
            "status": "success",
            "environments_path": path,
            "environment_count": len(environments),
        }

    def _load_manifest(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "asset_manifest.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_environments(self, environments: list) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "environments.json")
        with open(path, "w") as f:
            json.dump(environments, f, indent=2)
        return path
