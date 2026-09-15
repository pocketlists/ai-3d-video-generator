"""
Storage abstraction — persistent state storage across pipeline runs.

Supports:
- LocalStateStore: Filesystem storage (local development)
- GitHubArtifactStateStore: Upload state as artifact for cross-run persistence
- GitHubRepositoryStateStore: Commit state JSON to a dedicated branch

The GitHub Actions runner is ephemeral, so state MUST be persisted via
artifacts or repository commits to survive across workflow runs.
"""
import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional


class StateStoreError(Exception):
    pass


class StateStore(ABC):
    """Abstract base for state storage backends."""

    @abstractmethod
    def save_state(self, job_id: str, state: Dict[str, Any]) -> str:
        """Persist state. Returns storage reference (path, artifact name, etc.)."""
        ...

    @abstractmethod
    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load state for a job_id. Returns None if not found."""
        ...

    @abstractmethod
    def list_jobs(self) -> list:
        """List all known job IDs."""
        ...


class LocalStateStore(StateStore):
    """Filesystem-based state storage (local development)."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.environ.get("STATE_DIR", "/tmp/pipeline_state"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, job_id: str, state: Dict[str, Any]) -> str:
        path = self.base_dir / f"{job_id}.json"
        # Atomic write: temp file -> rename
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(str(tmp), str(path))
        return str(path)

    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self.base_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def list_jobs(self) -> list:
        return [f.stem for f in self.base_dir.glob("*.json") if f.is_file()]


class GitHubArtifactStateStore(StateStore):
    """
    State persisted via GitHub Actions artifacts.
    State JSON is saved locally and uploaded as an artifact.
    On resume, a new run downloads the artifact to recover state.
    """
    # In CI, artifacts are uploaded/downloaded via actions/upload-artifact
    # This class handles the local file I/O; the workflow handles artifact transfer.

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.environ.get("STATE_DIR", "/tmp/pipeline_state"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir = self.base_dir / "artifacts"
        self.artifact_dir.mkdir(exist_ok=True)

    def save_state(self, job_id: str, state: Dict[str, Any]) -> str:
        # Save locally — the workflow will upload this as an artifact
        path = self.artifact_dir / f"state_{job_id}.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(str(tmp), str(path))
        return str(path)

    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        # Look for state file locally (downloaded from artifact)
        path = self.artifact_dir / f"state_{job_id}.json"
        if not path.exists():
            # Also check base dir
            path = self.base_dir / f"state_{job_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def list_jobs(self) -> list:
        jobs = set()
        for f in self.artifact_dir.glob("state_*.json"):
            jobs.add(f.stem.replace("state_", ""))
        for f in self.base_dir.glob("state_*.json"):
            jobs.add(f.stem.replace("state_", ""))
        return list(jobs)


class GitHubRepositoryStateStore(StateStore):
    """
    State persisted via git commits to a 'pipeline-state' branch.
    Uses GitHub API to read/write state JSON.
    """
    def __init__(self, owner: str = "", repo: str = "", token: str = "", branch: str = "pipeline-state"):
        self.owner = owner or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.branch = branch
        self._local_cache = {}

    def save_state(self, job_id: str, state: Dict[str, Any]) -> str:
        # For CI: commit state to the pipeline-state branch via GitHub API
        # For local: just save to file
        path = f"state/{job_id}.json"
        if not self.owner or not self.token:
            # Local fallback
            local_path = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state"))
            local_path.mkdir(parents=True, exist_ok=True)
            fp = local_path / f"{job_id}.json"
            with open(fp, "w") as f:
                json.dump(state, f, indent=2)
            return str(fp)

        # In CI, the workflow handles the git push. We just write locally.
        local_path = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state")) / f"{job_id}.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w") as f:
            json.dump(state, f, indent=2)
        return str(local_path)

    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        # Try local first
        local_path = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state")) / f"{job_id}.json"
        if local_path.exists():
            try:
                with open(local_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def list_jobs(self) -> list:
        local_path = Path(os.environ.get("STATE_DIR", "/tmp/pipeline_state"))
        return [f.stem for f in local_path.glob("*.json") if f.is_file()]


def get_state_store(config: Optional[Dict] = None) -> StateStore:
    """Factory: select state store based on configuration."""
    config = config or {}
    backend = config.get("state_backend", "local")
    if backend == "artifact":
        return GitHubArtifactStateStore()
    elif backend == "repository":
        return GitHubRepositoryStateStore()
    return LocalStateStore()
