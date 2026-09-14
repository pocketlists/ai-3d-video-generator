"""
Prop worker — generates low-poly prop meshes.

Stage 7: Creates prop models (crates, barrels, etc.) for the scene.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from blender.low_poly_generator import LowPolyGenerator


class PropWorker(BaseWorker):
    stage_name = "props"

    def run(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "error": "No asset manifest found"}

        generator = LowPolyGenerator(seed=789)
        props = []
        for prop_spec in manifest.get("props", []):
            prop_type = prop_spec.get("type", "box")
            mesh = generator.generate_prop(prop_type)
            prop_data = {
                "name": prop_spec["name"],
                "type": prop_type,
                "mesh": mesh.to_dict(),
                "vertex_count": mesh.vertex_count(),
                "face_count": mesh.face_count(),
            }
            props.append(prop_data)
            self.logger.info(f"Generated prop: {prop_spec['name']} ({mesh.face_count()} faces)")

        path = self._save_props(props)
        return {
            "status": "success",
            "props_path": path,
            "prop_count": len(props),
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
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "props.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
        return path
