"""
Environment worker — uses 3D Asset API for real environment models.

Stage 6: Generates environment meshes via the configured 3D asset provider.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from providers.asset_provider import get_asset_provider
from utils.asset_validator import AssetValidator


class EnvironmentWorker(BaseWorker):
    stage_name = "environments"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        asset_provider = get_asset_provider(self.config)
        validator = AssetValidator()
        environments = []

        for env_spec in manifest.get("environments", []):
            name = env_spec["name"]
            prompt = env_spec.get("prompt", f"low-poly environment: {name}")

            asset = asset_provider.get_or_create(prompt, "environments", name)

            if asset and os.path.exists(asset.file_path):
                validation = validator.validate(asset.file_path)
                if validation["valid"]:
                    env_data = {
                        "name": name,
                        "asset_id": asset.asset_id,
                        "file_path": asset.file_path,
                        "format": asset.format,
                        "mesh_count": validation["mesh_count"],
                        "polygon_count": validation["polygon_count"],
                        "source": "3d_api",
                        "cached": True,
                    }
                else:
                    env_data = self._use_fallback(name)
            else:
                env_data = self._use_fallback(name)

            environments.append(env_data)

        path = self._save_environments(environments)
        return {
            "status": "success",
            "environments_path": path,
            "environment_count": len(environments),
        }

    def _use_fallback(self, name: str) -> Dict:
        from blender.low_poly_generator import LowPolyGenerator
        gen = LowPolyGenerator(seed=123)
        mesh = gen.generate_environment(name)
        return {
            "name": name,
            "mesh": mesh.to_dict(),
            "vertex_count": mesh.vertex_count(),
            "face_count": mesh.face_count(),
            "source": "fallback_low_poly",
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
        path = os.path.join(out_dir, "environments.json")
        with open(path, "w") as f:
            json.dump(environments, f, indent=2)
        return path
