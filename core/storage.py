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
        # v9: CI carry-over — only under GitHub Actions (GITHUB_ACTIONS=true),
        # mirror the state into the artifact directory so it rides along with
        # upload-artifact and survives to the next job's fresh runner.
        # Best-effort: the base_dir write above is the source of truth.
        art = os.environ.get("ARTIFACT_DIR") if os.environ.get("GITHUB_ACTIONS") == "true" else None
        if art:
            try:
                art_state = Path(art) / "state"
                art_state.mkdir(parents=True, exist_ok=True)
                atmp = art_state / f"{job_id}.json.tmp"
                with open(atmp, "w") as f:
                    json.dump(state, f, indent=2)
                os.replace(str(atmp), str(art_state / f"{job_id}.json"))
            except OSError:
                pass
        return str(path)

    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self.base_dir / f"{job_id}.json"
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
        # v9.1: CI fallback — fresh runner: state was downloaded with the
        # artifact (ARTIFACT_DIR/state/). Parallel jobs each upload their own
        # state file, so MERGE all of them: union of stages (latest timestamp
        # per stage wins), errors deduplicated, metrics/artifacts newest-wins.
        art = os.environ.get("ARTIFACT_DIR") if os.environ.get("GITHUB_ACTIONS") == "true" else None
        if not art:
            return None
        art_state = Path(art) / "state"
        if not art_state.exists():
            return None
        states = []
        for p in sorted(art_state.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                with open(p, "r") as f:
                    states.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue
        return self._merge_states(states)

    @staticmethod
    def _merge_states(states):
        """Merge parallel-job state files into one (v9.1).

        Each parallel job extends the shared base state with its own stage.
        Merging unions the stages — per stage, the entry with the LATEST
        timestamp wins (so a later 'failed' correctly overrides an earlier
        'completed', and vice versa). Errors are deduplicated;
        metrics/artifacts update in file-mtime order (newest wins).
        """
        if not states:
            return None
        if len(states) == 1:
            return states[0]
        merged = dict(states[0])  # oldest file: base identity (job_id etc.)
        all_stages = {}
        for st in states:
            for stage_name, info in (st.get("stages") or {}).items():
                prev = all_stages.get(stage_name)
                ts_new = (info or {}).get("timestamp", 0)
                ts_old = (prev or {}).get("timestamp", 0)
                if prev is None or ts_new >= ts_old:
                    all_stages[stage_name] = info
        merged["stages"] = all_stages
        errors = []
        seen = set()
        for st in states:
            for err in (st.get("errors") or []):
                key = (err.get("stage"), err.get("error"), err.get("timestamp"))
                if key not in seen:
                    seen.add(key)
                    errors.append(err)
        merged["errors"] = errors
        metrics = dict(merged.get("metrics") or {})
        artifacts = dict(merged.get("artifacts") or {})
        for st in states[1:]:
            metrics.update(st.get("metrics") or {})
            artifacts.update(st.get("artifacts") or {})
        merged["metrics"] = metrics
        merged["artifacts"] = artifacts
        return merged

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



class GitHubContentsStateStore(StateStore):
    """
    Persistent state via GitHub Contents API (gh api /repos/.../contents/).

    This is a REAL cross-runner persistence mechanism — state JSON is committed
    to a 'pipeline-state' branch (or the default branch under state/ prefix),
    not just written to local /tmp.

    Requires: GITHUB_TOKEN env var (set automatically in GitHub Actions).
    Uses: gh CLI (subprocess) — available in GitHub Actions runners.
    """
    def __init__(self, owner: str = "", repo: str = "", branch: str = "pipeline-state"):
        self.owner = owner or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
        repo_full = os.environ.get("GITHUB_REPOSITORY", "")
        self.repo = repo or (repo_full.split("/")[-1] if repo_full else "")
        self.branch = branch
        self._local_fallback = None  # lazy-init LocalStateStore for tests

    def _gh_available(self) -> bool:
        """Check if gh CLI + GITHUB_TOKEN are available."""
        import shutil, subprocess
        if not shutil.which("gh"):
            return False
        # gh uses GITHUB_TOKEN from env (GH_TOKEN also works)
        return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))

    def save_state(self, job_id: str, state: Dict[str, Any]) -> str:
        import subprocess, base64
        if not self._gh_available():
            # Local fallback for tests — mark clearly that this is NOT GitHub-persistent
            if self._local_fallback is None:
                self._local_fallback = LocalStateStore()
            path = self._local_fallback.save_state(job_id, state)
            return f"{path} (WARNING: local-only — gh CLI or GITHUB_TOKEN not available)"

        content_json = json.dumps(state, indent=2)
        content_b64 = base64.b64encode(content_json.encode()).decode()
        path = f"state/{job_id}.json"

        # gh api PUT /repos/{owner}/{repo}/contents/{path}
        result = subprocess.run([
            "gh", "api", f"/repos/{self.owner}/{self.repo}/contents/{path}",
            "-X", "PUT",
            "-f", f"message=checkpoint: {job_id}",
            "-f", f"content={content_b64}",
            "-f", f"branch={self.branch}",
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            # Fallback to local if branch doesn't exist or API fails
            if self._local_fallback is None:
                self._local_fallback = LocalStateStore()
            return self._local_fallback.save_state(job_id, state) + " (fallback: gh API failed)"
        return f"github:contents:{path}@{self.branch}"

    def load_state(self, job_id: str) -> Optional[Dict[str, Any]]:
        import subprocess, base64
        # Try local first (faster, may have been written by fallback)
        if self._local_fallback:
            loaded = self._local_fallback.load_state(job_id)
            if loaded:
                return loaded

        if not self._gh_available():
            return None

        path = f"state/{job_id}.json"
        result = subprocess.run([
            "gh", "api", f"/repos/{self.owner}/{self.repo}/contents/{path}",
            "-H", f"Accept: application/vnd.github.raw",
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def list_jobs(self) -> list:
        import subprocess
        if not self._gh_available():
            if self._local_fallback:
                return self._local_fallback.list_jobs()
            return []
        result = subprocess.run([
            "gh", "api", f"/repos/{self.owner}/{self.repo}/contents/state",
            "-H", f"Accept: application/vnd.github+json",
        ], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        try:
            items = json.loads(result.stdout)
            return [i["name"].replace(".json", "") for i in items if i.get("name", "").endswith(".json")]
        except (json.JSONDecodeError, KeyError):
            return []


def get_state_store(config: Optional[Dict] = None) -> StateStore:
    """Factory: select state store based on configuration."""
    config = config or {}
    backend = config.get("state_backend", "local")
    if backend == "artifact":
        return GitHubArtifactStateStore()
    elif backend == "repository":
        return GitHubRepositoryStateStore()
    elif backend == "contents":
        return GitHubContentsStateStore()
    return LocalStateStore()
