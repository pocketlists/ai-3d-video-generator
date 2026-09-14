"""
Character worker — generates low-poly character meshes.

Stage 5: Creates character meshes using the low-poly generator,
saves them as mesh data JSON for the Blender assembly stage.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from blender.low_poly_generator import LowPolyGenerator


class CharacterWorker(BaseWorker):
    stage_name = "characters"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        generator = LowPolyGenerator(seed=42)
        characters = []
        for char_spec in manifest.get("characters", []):
            mesh = generator.generate_character(char_spec["name"])
            char_data = {
                "name": char_spec["name"],
                "mesh": mesh.to_dict(),
                "vertex_count": mesh.vertex_count(),
                "face_count": mesh.face_count(),
            }
            characters.append(char_data)
            self.logger.info(f"Generated character: {char_spec['name']} ({mesh.vertex_count()} verts)")

        path = self._save_characters(characters)
        return {
            "status": "success",
            "characters_path": path,
            "character_count": len(characters),
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
