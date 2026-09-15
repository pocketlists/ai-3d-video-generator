"""
Prop worker — uses 3D Asset API for real prop models.

Stage 7: Generates prop meshes via the configured 3D asset provider.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from providers.asset_provider import get_asset_provider
from utils.asset_validator import AssetValidator


class PropWorker(BaseWorker):
    stage_name = "props"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        asset_provider = get_asset_provider(self.config)
        validator = AssetValidator()
        props = []

        for prop_spec in manifest.get("props", []):
            name = prop_spec["name"]
            prompt = prop_spec.get("prompt", f"low-poly prop: {name}")

            asset = asset_provider.get_or_create(prompt, "props", name)

            if asset and os.path.exists(asset.file_path):
                validation = validator.validate(asset.file_path)
                if validation["valid"]:
                    prop_data = {
                        "name": name,
                        "asset_id": asset.asset_id,
                        "file_path": asset.file_path,
                        "format": asset.format,
                        "mesh_count": validation["mesh_count"],
                        "source": "3d_api",
                        "cached": True,
                    }
                else:
                    prop_data = self._use_fallback(name, prop_spec.get("type", "box"))
            else:
                prop_data = self._use_fallback(name, prop_spec.get("type", "box"))

            props.append(prop_data)

        path = self._save_props(props)
        return {
            "status": "success",
            "props_path": path,
            "prop_count": len(props),
        }

    def _use_fallback(self, name: str, prop_type: str) -> Dict:
        from blender.low_poly_generator import LowPolyGenerator
        gen = LowPolyGenerator(seed=789)
        mesh = gen.generate_prop(prop_type)
        return {
            "name": name,
            "type": prop_type,
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

    def _save_props(self, props: list) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(out_dir, "props.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
        return path
