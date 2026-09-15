"""
State manager — tracks pipeline state with resume support.

Supports resumable states:
- RECEIVED, PLANNING, SCRIPTING, ASSET_GENERATION
- CHARACTERS, ENVIRONMENT, PROPS, ANIMATION, CAMERA, LIGHTING
- TTS, MUSIC, SFX, LIPSYNC, BLENDER_ASSEMBLY, RENDERING
- QUALITY_CHECK, FFMPEG, DELIVERY, COMPLETED
- FAILED, RETRYING
- WAITING_FOR_EXTERNAL_RESPONSE
- CANCELLED

The pipeline can resume from the last successful stage after failure.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# All valid pipeline states
VALID_STATES = [
    "RECEIVED", "PLANNING", "SCRIPTING", "ASSET_GENERATION",
    "CHARACTERS", "ENVIRONMENT", "PROPS", "ANIMATION", "CAMERA", "LIGHTING",
    "TTS", "MUSIC", "SFX", "LIPSYNC", "BLENDER_ASSEMBLY", "RENDERING",
    "QUALITY_CHECK", "FFMPEG", "DELIVERY", "COMPLETED",
    "FAILED", "RETRYING",
    "WAITING_FOR_EXTERNAL_RESPONSE",
    "CANCELLED",
]


class StateManager:
    """Manages pipeline state persisted as JSON for resumability."""

    DEFAULT_STATE_DIR = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state"))

    def __init__(self, run_id: Optional[str] = None, state_dir: Optional[str] = None):
        self.run_id = run_id or os.environ.get("GITHUB_RUN_ID", "local")
        self.state_dir = Path(state_dir) if state_dir else self.DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"state_{self.run_id}.json"
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "run_id": self.run_id,
            "created_at": time.time(),
            "stages": {},
            "artifacts": {},
            "errors": [],
            "metrics": {},
            "pending_escalations": [],
            "job_id": None,
            "current_state": "RECEIVED",
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
        # Update current_state if it's a valid state
        if status in VALID_STATES:
            self._state["current_state"] = status
        self.save()

    def get_stage_status(self, stage: str) -> Optional[Dict]:
        return self._state["stages"].get(stage)

    def is_stage_complete(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] in ("completed", "COMPLETED")

    def is_stage_waiting(self, stage: str) -> bool:
        """Check if a stage is waiting for external response."""
        info = self.get_stage_status(stage)
        return info is not None and info["status"] == "WAITING_FOR_EXTERNAL_RESPONSE"

    def is_stage_failed(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] in ("failed", "FAILED")

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

    def get_resume_point(self) -> Optional[str]:
        """Find the last incomplete stage to resume from."""
        from controller.pipeline import PIPELINE_STAGES
        for stage in PIPELINE_STAGES:
            if not self.is_stage_complete(stage.name):
                return stage.name
        return None

    def can_resume(self) -> bool:
        """Check if the pipeline can be resumed from a previous state."""
        return any(
            self.is_stage_complete(s.name)
            for s in []
        ) or self.get_resume_point() is not None

    def add_pending_escalation(self, job_id: str, stage: str, error: str,
                                message_id: Optional[int] = None) -> None:
        """Record a pending escalation waiting for external response."""
        self._state["pending_escalations"].append({
            "job_id": job_id,
            "stage": stage,
            "error": error,
            "message_id": message_id,
            "timestamp": time.time(),
        })
        self.save()

    def resolve_escalation(self, job_id: str, stage: str, response: str) -> None:
        """Mark an escalation as resolved."""
        self._state["pending_escalations"] = [
            e for e in self._state.get("pending_escalations", [])
            if not (e.get("job_id") == job_id and e.get("stage") == stage)
        ]
        self.set_stage_status(stage, "completed", {"external_response": response})
        self.logger_info(f"Escalation resolved: {job_id}/{stage}")

    def logger_info(self, msg: str) -> None:
        """Log a message (simplified to avoid circular import)."""
        print(f"[StateManager] {msg}")

    def get_pending_escalations(self) -> List[Dict]:
        return self._state.get("pending_escalations", [])

    def has_pending_escalations(self) -> bool:
        return len(self._state.get("pending_escalations", [])) > 0
