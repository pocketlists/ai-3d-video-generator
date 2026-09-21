"""
State manager — proper state machine with transitions, checkpoints, resume.

Canonical states:
RECEIVED → PLANNING → SCRIPTING → ASSET_SEARCH → ... → COMPLETED
                                         ↘ FAILED → RETRYING
                                         ↘ WAITING_FOR_EXTERNAL_RESPONSE
                                         ↘ CANCELLED

Valid transitions enforced. State persisted via storage abstraction.
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.storage import StateStore, get_state_store
from controller.checkpoint import CheckpointManager, Checkpoint
from utils.logger import PipelineLogger


VALID_STATES = [
    "RECEIVED", "PLANNING", "SCRIPTING", "ASSET_SEARCH", "ASSET_GENERATION",
    "ASSET_VALIDATION", "CHARACTERS", "ENVIRONMENT", "PROPS",
    "ANIMATION", "CAMERA", "LIGHTING", "TTS", "MUSIC", "SFX", "LIPSYNC",
    "BLENDER_ASSEMBLY", "RENDER_PREPARATION", "RENDERING",
    "QUALITY_CHECK", "FFMPEG", "DELIVERY", "COMPLETED",
    "FAILED", "RETRYING", "WAITING_FOR_EXTERNAL_RESPONSE", "CANCELLED",
]

# Valid state transitions
TRANSITIONS = {
    "RECEIVED": ["PLANNING", "FAILED", "CANCELLED"],
    "PLANNING": ["SCRIPTING", "FAILED", "WAITING_FOR_EXTERNAL_RESPONSE", "CANCELLED"],
    "SCRIPTING": ["ASSET_SEARCH", "FAILED", "CANCELLED"],
    "ASSET_SEARCH": ["ASSET_GENERATION", "CHARACTERS", "ENVIRONMENT", "PROPS", "FAILED", "CANCELLED"],
    "ASSET_GENERATION": ["ASSET_VALIDATION", "FAILED", "CANCELLED"],
    "ASSET_VALIDATION": ["CHARACTERS", "ENVIRONMENT", "PROPS", "FAILED", "CANCELLED"],
    "CHARACTERS": ["ANIMATION", "FAILED", "CANCELLED"],
    "ENVIRONMENT": ["ANIMATION", "CAMERA", "LIGHTING", "FAILED", "CANCELLED"],
    "PROPS": ["ANIMATION", "FAILED", "CANCELLED"],
    "ANIMATION": ["BLENDER_ASSEMBLY", "FAILED", "CANCELLED"],
    "CAMERA": ["BLENDER_ASSEMBLY", "FAILED", "CANCELLED"],
    "LIGHTING": ["BLENDER_ASSEMBLY", "FAILED", "CANCELLED"],
    "TTS": ["LIPSYNC", "FFMPEG", "FAILED", "CANCELLED"],
    "MUSIC": ["FFMPEG", "FAILED", "CANCELLED"],
    "SFX": ["FFMPEG", "FAILED", "CANCELLED"],
    "LIPSYNC": ["BLENDER_ASSEMBLY", "FAILED", "CANCELLED"],
    "BLENDER_ASSEMBLY": ["RENDER_PREPARATION", "FAILED", "CANCELLED"],
    "RENDER_PREPARATION": ["RENDERING", "FAILED", "CANCELLED"],
    "RENDERING": ["QUALITY_CHECK", "FAILED", "CANCELLED"],
    "QUALITY_CHECK": ["FFMPEG", "FAILED", "RETRYING", "CANCELLED"],
    "FFMPEG": ["DELIVERY", "FAILED", "CANCELLED"],
    "DELIVERY": ["COMPLETED", "FAILED", "CANCELLED"],
    "FAILED": ["RETRYING", "WAITING_FOR_EXTERNAL_RESPONSE", "CANCELLED"],
    "RETRYING": ["RECEIVED", "PLANNING", "SCRIPTING", "ASSET_SEARCH", "FAILED"],
    "WAITING_FOR_EXTERNAL_RESPONSE": ["RETRYING", "COMPLETED", "CANCELLED", "FAILED"],
    "COMPLETED": [],
    "CANCELLED": [],
}


class StateManager:
    """Manages pipeline state with state machine, checkpoints, and resume."""

    def __init__(self, run_id: Optional[str] = None, state_dir: Optional[str] = None,
                 job_id: Optional[str] = None):
        self.logger = PipelineLogger("state_manager")
        # run_id and job_id are aliases; job_id takes precedence
        self.job_id = job_id or run_id or os.environ.get("JOB_ID", "") \
            or os.environ.get("GITHUB_RUN_ID", "local")
        self.run_id = self.job_id  # backward compat alias
        self.state_dir = state_dir
        # Pass state_dir to the store so tests with tmp_path don't share state
        backend = os.environ.get("STATE_BACKEND", "local")
        if state_dir and backend == "local":
            from core.storage import LocalStateStore
            self.store = LocalStateStore(base_dir=state_dir)
        else:
            self.store = get_state_store({"state_backend": backend})
        self.checkpoint_mgr = CheckpointManager(self.job_id or "default", state_dir)

        self._state: Dict[str, Any] = {
            "job_id": self.job_id or f"job_{int(time.time())}",
            "run_id": self.job_id,  # backward compat key
            "created_at": time.time(),
            "current_state": "RECEIVED",
            "stages": {},
            "artifacts": {},
            "errors": [],
            "metrics": {},
            "pending_escalations": [],
        }

        # Try loading existing state
        if self.job_id:
            loaded = self.store.load_state(self.job_id)
            if loaded:
                self._state = loaded
                # v9: normalize — a loaded state (e.g. minimal CI artifact
                # state) may be missing optional keys; fill them defensively
                # instead of crashing later with KeyError.
                self._state.setdefault("job_id", self.job_id)
                self._state.setdefault("created_at", time.time())
                self._state.setdefault("current_state", "RECEIVED")
                self._state.setdefault("stages", {})
                self._state.setdefault("artifacts", {})
                self._state.setdefault("errors", [])
                self._state.setdefault("metrics", {})
                self._state.setdefault("pending_escalations", [])
                self.logger.info(f"Loaded existing state for job: {self.job_id}")

    def transition(self, new_state: str) -> bool:
        """Transition to a new state. Validates transition is allowed."""
        current = self._state.get("current_state", "RECEIVED")
        if new_state not in VALID_STATES:
            self.logger.error(f"Invalid state: {new_state}")
            return False
        allowed = TRANSITIONS.get(current, [])
        if new_state not in allowed:
            self.logger.error(f"Invalid transition: {current} → {new_state}")
            return False
        self._state["current_state"] = new_state
        self._save()
        self.logger.info(f"State transition: {current} → {new_state}")
        return True

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is valid."""
        return to_state in TRANSITIONS.get(from_state, [])

    def set_stage_status(self, stage: str, status: str, data: Optional[Dict] = None) -> None:
        """Set stage status and save checkpoint."""
        self._state["stages"][stage] = {
            "status": status,
            "timestamp": time.time(),
            "data": data or {},
        }
        # Also update current_state if valid
        if status in VALID_STATES:
            self._state["current_state"] = status
        # Save checkpoint
        cp = Checkpoint(
            job_id=self.job_id, stage=stage, status=status,
            input_hash=data.get("input_hash", "") if data else "",
            output_files=data.get("output_files", []) if data else [],
            artifact_refs=data.get("artifact_refs", []) if data else [],
            metadata=data or {},
        )
        self.checkpoint_mgr.save_checkpoint(cp)
        self._save()

    @property
    def state_file(self) -> Path:
        """Backward-compat: path to the state JSON file."""
        base = self.state_dir or "/tmp/pipeline_state"
        return Path(base) / f"{self.job_id}.json"

    def get_stage_status(self, stage: str) -> Optional[Dict]:
        return self._state["stages"].get(stage)

    def is_stage_complete(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] in ("completed", "COMPLETED")

    def is_stage_waiting(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] == "WAITING_FOR_EXTERNAL_RESPONSE"

    def is_stage_failed(self, stage: str) -> bool:
        info = self.get_stage_status(stage)
        return info is not None and info["status"] in ("failed", "FAILED")

    def mark_completed(self, stage: str, data: Optional[Dict] = None) -> None:
        self.set_stage_status(stage, "completed", data)

    def mark_failed(self, stage: str, error: str, recoverable: bool = True) -> None:
        self._state["errors"].append({
            "stage": stage, "error": error, "recoverable": recoverable,
            "timestamp": time.time(),
        })
        self.set_stage_status(stage, "FAILED", {"error": error})

    def mark_waiting(self, stage: str, error: str, resume_token: str = "",
                     message_id: Optional[int] = None) -> None:
        """Mark stage as waiting for external response (Telegram escalation)."""
        self._state["pending_escalations"].append({
            "job_id": self.job_id,
            "stage": stage,
            "error": error,
            "resume_token": resume_token,
            "message_id": message_id,
            "timestamp": time.time(),
        })
        self.set_stage_status(stage, "WAITING_FOR_EXTERNAL_RESPONSE", {
            "error": error, "resume_token": resume_token,
        })

    def resume_stage(self, stage: str, response: str) -> None:
        """Resolve escalation and mark stage for retry."""
        self._state["pending_escalations"] = [
            e for e in self._state.get("pending_escalations", [])
            if e.get("stage") != stage
        ]
        self.set_stage_status(stage, "RETRYING", {"external_response": response})
        self.logger.info(f"Escalation resolved for {stage}, resuming")

    def get_resume_point(self) -> Optional[str]:
        """Find the last incomplete stage to resume from."""
        from controller.pipeline import PIPELINE_STAGES
        for stage in PIPELINE_STAGES:
            if not self.is_stage_complete(stage.name):
                return stage.name
        return None

    def can_resume(self) -> bool:
        """Check if pipeline can be resumed."""
        return self.get_resume_point() is not None

    def record_artifact(self, name: str, path: str, size: int = 0) -> None:
        self._state["artifacts"][name] = {
            "path": path, "size": size, "timestamp": time.time(),
        }
        self._save()

    def get_artifact(self, name: str) -> Optional[Dict]:
        return self._state["artifacts"].get(name)

    def record_error(self, stage: str, error: str, recoverable: bool = True) -> None:
        self._state["errors"].append({
            "stage": stage, "error": error, "recoverable": recoverable,
            "timestamp": time.time(),
        })
        self._save()

    def record_metric(self, key: str, value: Any) -> None:
        self._state["metrics"][key] = value
        self._save()

    def get_metrics(self) -> Dict[str, Any]:
        return self._state["metrics"]

    def get_full_state(self) -> Dict[str, Any]:
        return self._state


    def resolve_escalation(self, job_id: str, stage: str, response: str) -> None:
        """Backward-compat alias for resume_stage()."""
        self.resume_stage(stage, response)

    def add_pending_escalation(self, job_id: str, stage: str, error: str,
                                message_id: Optional[int] = None) -> None:
        """Backward-compat alias for mark_waiting()."""
        self.mark_waiting(stage, error, message_id=message_id)

    def get_pending_escalations(self) -> List[Dict]:
        return self._state.get("pending_escalations", [])

    def has_pending_escalations(self) -> bool:
        return len(self._state.get("pending_escalations", [])) > 0

    def save_checkpoint(self) -> str:
        """Persist state to storage. Returns storage reference."""
        return self._save()

    def load_checkpoint(self) -> Optional[Dict]:
        """Load state from storage."""
        if not self.job_id:
            return None
        loaded = self.store.load_state(self.job_id)
        if loaded:
            self._state = loaded
            return loaded
        return None

    def _save(self) -> str:
        """Save state to persistent storage."""
        self._state["updated_at"] = time.time()
        try:
            return self.store.save_state(self.job_id, self._state)
        except Exception as e:
            self.logger.error(f"State save failed: {e}")
            return ""

    def export_json(self) -> str:
        return json.dumps(self._state, indent=2)
