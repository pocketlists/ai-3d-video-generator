"""
Character worker — uses 3D Asset API to generate real character models.

Stage 5: Generates character meshes via the configured 3D asset provider.
Falls back to low_poly_generator if no API is configured.
Caches assets for reuse across scenes.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from providers.asset_provider import get_asset_provider
from utils.asset_validator import AssetValidator


class CharacterWorker(BaseWorker):
    stage_name = "characters"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        asset_provider = get_asset_provider(self.config)
        validator = AssetValidator()
        characters = []

        for char_index, char_spec in enumerate(manifest.get("characters", []), start=1):
            name = char_spec["name"]
            prompt = char_spec.get("prompt", f"low-poly character: {name}")

            # Try 3D asset API first
            asset = asset_provider.get_or_create(prompt, "characters", name)

            if asset and os.path.exists(asset.file_path):
                # Validate the downloaded asset
                validation = validator.validate(asset.file_path)
                if validation["valid"]:
                    char_data = {
                        "name": name,
                        "character_id": f"character_{char_index:03d}",
                        "asset_id": asset.asset_id,
                        "file_path": asset.file_path,
                        "format": asset.format,
                        "mesh_count": validation["mesh_count"],
                        "polygon_count": validation["polygon_count"],
                        "rig_status": "rigged" if validation["rig_present"] else "static",
                        "texture_status": "textured" if validation["texture_count"] > 0 else "untextured",
                        "source": "3d_api",
                        "cached": True,
                    }
                    self.logger.info(f"Character generated via 3D API: {name} "
                                   f"({validation['mesh_count']} meshes, {validation['polygon_count']} polys)")
                else:
                    self.logger.warning(f"Asset validation failed for {name}: {validation['issues']}")
                    char_data = self._use_fallback(name, char_index)
            else:
                self.logger.info(f"3D API not available, using fallback for: {name}")
                char_data = self._use_fallback(name, char_index)

            characters.append(char_data)

        path = self._save_characters(characters)
        return {
            "status": "success",
            "characters_path": path,
            "character_count": len(characters),
            "api_used": any(c.get("source") == "3d_api" for c in characters),
        }

    def _use_fallback(self, name: str, char_index: int = 0) -> Dict:
        """Fallback to low_poly_generator when 3D API is unavailable."""
        from blender.low_poly_generator import LowPolyGenerator
        gen = LowPolyGenerator(seed=42)
        mesh = gen.generate_character(name)
        return {
            "name": name,
            "character_id": f"character_{char_index:03d}" if char_index else None,
            "mesh": mesh.to_dict(),
            "vertex_count": mesh.vertex_count(),
            "face_count": mesh.face_count(),
            "source": "fallback_low_poly",
            "cached": False,
        }

    def _load_manifest(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "asset_manifest.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_characters(self, characters: list) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "characters.json")
        with open(path, "w") as f:
            json.dump(characters, f, indent=2)
        return path
