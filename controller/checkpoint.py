"""
Checkpoint system — atomic checkpoint writing for pipeline stages.

Every major stage produces a checkpoint.json with:
- job_id, stage, status, timestamp
- input_hash, output_files, artifact_refs, metadata

Checkpoints are written atomically (temp file → fsync → rename)
to prevent partial writes from corrupting state.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import PipelineLogger


class Checkpoint:
    """Represents a single pipeline checkpoint."""

    def __init__(self, job_id: str, stage: str, status: str = "pending",
                 input_hash: str = "", output_files: List[str] = None,
                 artifact_refs: List[str] = None, metadata: Dict[str, Any] = None):
        self.job_id = job_id
        self.stage = stage
        self.status = status
        self.timestamp = time.time()
        self.input_hash = input_hash
        self.output_files = output_files or []
        self.artifact_refs = artifact_refs or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "status": self.status,
            "timestamp": self.timestamp,
            "input_hash": self.input_hash,
            "output_files": self.output_files,
            "artifact_refs": self.artifact_refs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Checkpoint":
        cp = cls(
            job_id=data.get("job_id", ""),
            stage=data.get("stage", ""),
            status=data.get("status", "pending"),
            input_hash=data.get("input_hash", ""),
            output_files=data.get("output_files", []),
            artifact_refs=data.get("artifact_refs", []),
            metadata=data.get("metadata", {}),
        )
        cp.timestamp = data.get("timestamp", time.time())
        return cp


class CheckpointManager:
    """Manages atomic checkpoint writing and loading."""

    def __init__(self, job_id: str, checkpoint_dir: Optional[str] = None):
        self.job_id = job_id
        self.checkpoint_dir = Path(checkpoint_dir or
                                   os.environ.get("STATE_DIR", "/tmp/pipeline_state"))
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.logger = PipelineLogger("checkpoint")

    def save_checkpoint(self, checkpoint: Checkpoint) -> str:
        """Atomically save a checkpoint. Returns the file path."""
        path = self.checkpoint_dir / f"checkpoint_{self.job_id}_{checkpoint.stage}.json"

        # Atomic write: write to temp file, fsync, rename
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.rename(str(tmp_path), str(path))
            self.logger.info(f"Checkpoint saved: {checkpoint.stage} ({checkpoint.status})")
            return str(path)
        except Exception as e:
            self.logger.error(f"Checkpoint save failed: {e}")
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def load_checkpoint(self, stage: str) -> Optional[Checkpoint]:
        """Load a checkpoint for a stage."""
        path = self.checkpoint_dir / f"checkpoint_{self.job_id}_{stage}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return Checkpoint.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Checkpoint load failed for {stage}: {e}")
            return None

    def load_all_checkpoints(self) -> Dict[str, Checkpoint]:
        """Load all checkpoints for this job."""
        checkpoints = {}
        for f in self.checkpoint_dir.glob(f"checkpoint_{self.job_id}_*.json"):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                cp = Checkpoint.from_dict(data)
                checkpoints[cp.stage] = cp
            except (json.JSONDecodeError, IOError):
                continue
        return checkpoints

    def is_stage_completed(self, stage: str) -> bool:
        """Check if a stage has a completed checkpoint."""
        cp = self.load_checkpoint(stage)
        return cp is not None and cp.status == "completed"

    def get_resume_point(self) -> Optional[str]:
        """Find the last incomplete stage to resume from."""
        from controller.pipeline import PIPELINE_STAGES
        for stage in PIPELINE_STAGES:
            if not self.is_stage_completed(stage.name):
                return stage.name
        return None

    @staticmethod
    def compute_hash(data: Any) -> str:
        """Compute SHA256 hash of input data for checkpoint integrity."""
        if isinstance(data, str):
            return hashlib.sha256(data.encode()).hexdigest()[:16]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
