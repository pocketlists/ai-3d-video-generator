"""
State manager — tracks pipeline state across GitHub Actions jobs.

Uses GitHub Actions artifacts and a JSON state file to share state
between jobs, since GitHub-hosted runners don't share filesystems.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


class StateManager:
    """Manages pipeline state persisted as JSON artifacts."""

    DEFAULT_STATE_DIR = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state"))

    def __init__(self, run_id: Optional[str] = None, state_dir: Optional[str] = None):
        self.run_id = run_id or os.environ.get("GITHUB_RUN_ID", "local")
        self.state_dir = Path(state_dir) if state_dir else self.DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"state_{self.run_id}.json"
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {
            "run_id": self.run_id,
            "created_at": time.time(),
            "stages": {},
            "artifacts": {},
            "errors": [],
            "metrics": {},
        }

    def save(self) -> None:
        self._state["updated_at"] = time.time()
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def set_stage_status(self, stage: str, status: str, data: Optional[Dict] = None) -> None:
        self._state["stages"][stage] = {
            "status": status,
            "timestamp": time.time(),
            "data": data or {},
        }
        self.save()

    def get_stage_status(self, stage: str) -> Optional[Dict]:
        return self._state["stages"].get(stage)

    def is_stage_complete(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] == "completed"

    def record_artifact(self, name: str, path: str, size: int = 0) -> None:
        self._state["artifacts"][name] = {
            "path": path,
            "size": size,
            "timestamp": time.time(),
        }
        self.save()

    def get_artifact(self, name: str) -> Optional[Dict]:
        return self._state["artifacts"].get(name)

    def record_error(self, stage: str, error: str, recoverable: bool = True) -> None:
        self._state["errors"].append({
            "stage": stage,
            "error": error,
            "recoverable": recoverable,
            "timestamp": time.time(),
        })
        self.save()

    def record_metric(self, key: str, value: Any) -> None:
        self._state["metrics"][key] = value
        self.save()

    def get_metrics(self) -> Dict[str, Any]:
        return self._state["metrics"]

    def get_full_state(self) -> Dict[str, Any]:
        return self._state

    def export_json(self) -> str:
        return json.dumps(self._state, indent=2)
