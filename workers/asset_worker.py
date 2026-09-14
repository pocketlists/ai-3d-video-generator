"""Asset worker — collects and catalogues all required assets.

Stage 4: Reads the script breakdown and creates an asset manifest
listing all characters, environments, props, and audio assets needed.
"""
import json
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from utils.file_validator import validate_file_exists


class AssetWorker(BaseWorker):
    stage_name = "asset_collection"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        manifest = self._build_manifest(breakdown)
        path = self._save_manifest(manifest)
        return {
            "status": "success",
            "manifest_path": path,
            "total_assets": manifest["summary"]["total"],
            "characters": manifest["summary"]["characters"],
            "environments": manifest["summary"]["environments"],
            "props": manifest["summary"]["props"],
            "audio": manifest["summary"]["audio"],
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _build_manifest(self, breakdown: Dict) -> Dict[str, Any]:
        characters = set()
        environments = set()
        props = set()

        for shot in breakdown.get("shots", []):
            for char in shot.get("characters", []):
                characters.add(char.get("name", "unnamed"))
            env = shot.get("environment", {})
            if env:
                environments.add(env.get("type", "default"))
            for prop in shot.get("props", []):
                props.add(prop.get("name", "unnamed"))

        return {
            "characters": [
                {"name": c, "type": "low_poly_humanoid", "status": "pending"}
                for c in sorted(characters)
            ],
            "environments": [
                {"name": e, "type": "low_poly_terrain", "status": "pending"}
                for e in sorted(environments)
            ],
            "props": [
                {"name": p, "type": "low_poly_prop", "status": "pending"}
                for p in sorted(props)
            ],
            "audio": {
                "voice": True,
                "music": True,
                "sfx": True,
            },
            "summary": {
                "characters": len(characters),
                "environments": len(environments),
                "props": len(props),
                "audio": 3,
                "total": len(characters) + len(environments) + len(props) + 3,
            },
        }

    def _save_manifest(self, manifest: Dict) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "asset_manifest.json")
        with open(path, "w") as f:
            json.dump(manifest, f, indent=2)
        return path
