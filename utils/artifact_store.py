"""
Artifact store — manages file artifacts across pipeline stages.

In GitHub Actions, artifacts are passed between jobs via upload/download.
Locally, artifacts are stored in a shared directory.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional


class ArtifactStore:
    """Store and retrieve pipeline artifacts."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.base_dir / "manifest.json"
        self._manifest: Dict[str, Dict] = self._load_manifest()

    def _load_manifest(self) -> Dict:
        if self.manifest_file.exists():
            with open(self.manifest_file, "r") as f:
                return json.load(f)
        return {}

    def _save_manifest(self) -> None:
        with open(self.manifest_file, "w") as f:
            json.dump(self._manifest, f, indent=2)

    def store(self, name: str, source_path: str) -> str:
        """Store a file or directory as a named artifact."""
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")
        dest = self.base_dir / name
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

        if dest.is_file():
            size = dest.stat().st_size
        else:
            size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
        self._manifest[name] = {
            "path": str(dest),
            "size_bytes": size,
            "source": source_path,
        }
        self._save_manifest()
        return str(dest)

    def retrieve(self, name: str) -> str:
        """Get the path to a stored artifact."""
        if name not in self._manifest:
            raise KeyError(f"Artifact not found: {name}")
        path = self._manifest[name]["path"]
        if not Path(path).exists():
            raise FileNotFoundError(f"Artifact file missing on disk: {path}")
        return path

    def list_artifacts(self) -> List[str]:
        return list(self._manifest.keys())

    def has_artifact(self, name: str) -> bool:
        return name in self._manifest

    def get_artifact_info(self, name: str) -> Optional[Dict]:
        return self._manifest.get(name)

    def cleanup(self) -> None:
        """Remove all stored artifacts."""
        for name in list(self._manifest.keys()):
            path = Path(self._manifest[name]["path"])
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        self._manifest.clear()
        self._save_manifest()

    def total_size(self) -> int:
        return sum(info.get("size_bytes", 0) for info in self._manifest.values())
