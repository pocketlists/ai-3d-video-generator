"""v9 tests: state carried through artifacts — CI fresh-runner dependency fix.

Regression for: "Dependency 'receive_request' not complete for stage
'ai_planning'" — every GitHub Actions job runs on a fresh runner, so
state must travel with the artifacts (ARTIFACT_DIR/state/).
"""
import json
import os
from pathlib import Path


class TestStateCarriedThroughArtifacts:
    def test_save_mirrors_to_artifact_dir(self, tmp_path, monkeypatch):
        art = tmp_path / "art"
        state_dir = tmp_path / "state"
        art.mkdir(); state_dir.mkdir()
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(state_dir))
        from core.storage import LocalStateStore
        store = LocalStateStore(base_dir=str(state_dir))
        store.save_state("job_x", {"job_id": "job_x", "stages": {}})
        # base dir write
        assert (state_dir / "job_x.json").exists()
        # artifact mirror (uploaded with upload-artifact, downloaded by next job)
        assert (art / "state" / "job_x.json").exists()

    def test_load_falls_back_to_artifact_state_fresh_runner(self, tmp_path, monkeypatch):
        # Fresh runner: STATE_DIR empty; artifact downloaded into ARTIFACT_DIR
        art = tmp_path / "art"
        fresh_state = tmp_path / "fresh_state"
        art.mkdir(); fresh_state.mkdir()
        (art / "state").mkdir()
        (art / "state" / "job_from_receive.json").write_text(json.dumps({
            "job_id": "job_from_receive",
            "stages": {"receive_request": {"status": "completed"}},
        }))
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(fresh_state))
        from core.storage import LocalStateStore
        store = LocalStateStore(base_dir=str(fresh_state))
        loaded = store.load_state("some_other_runner_job_id")
        assert loaded is not None
        assert loaded["stages"]["receive_request"]["status"] == "completed"

    def test_no_ci_no_artifact_fallback(self, tmp_path, monkeypatch):
        # Local/test env (GITHUB_ACTIONS unset) must NOT use artifact fallback
        art = tmp_path / "art"; art.mkdir()
        (art / "state").mkdir()
        (art / "state" / "x.json").write_text(json.dumps({"job_id": "x"}))
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        from core.storage import LocalStateStore
        store = LocalStateStore(base_dir=str(tmp_path / "s2"))
        (tmp_path / "s2").mkdir(exist_ok=True)
        assert store.load_state("nope") is None

    def test_dependency_check_passes_on_fresh_runner(self, tmp_path, monkeypatch):
        """Exact CI scenario that failed: planning job, fresh state dir,
        artifact contains receive's state."""
        art = tmp_path / "art"; art.mkdir()
        fresh_state = tmp_path / "state"; fresh_state.mkdir()
        (art / "state").mkdir()
        (art / "state" / "job_r.json").write_text(json.dumps({
            "job_id": "job_r",
            "stages": {"receive_request": {"status": "completed"}},
        }))
        (art / "request.json").write_text(json.dumps(
            {"job_id": "job_r", "prompt": "p", "style": "s"}))
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(fresh_state))
        monkeypatch.setenv("STATE_BACKEND", "local")
        monkeypatch.setenv("PIPELINE_MODE", "test")
        monkeypatch.delenv("JOB_ID", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        from controller.state_manager import StateManager
        sm = StateManager()
        assert sm.is_stage_complete("receive_request") is True


class TestStateNormalization:
    def test_minimal_loaded_state_gets_required_keys(self, tmp_path, monkeypatch):
        art = tmp_path / "art"; art.mkdir()
        fresh_state = tmp_path / "state"; fresh_state.mkdir()
        (art / "state").mkdir()
        (art / "state" / "m.json").write_text(json.dumps({"job_id": "m"}))
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(fresh_state))
        monkeypatch.delenv("JOB_ID", raising=False)
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
        from controller.state_manager import StateManager
        sm = StateManager()
        # These must NOT raise KeyError even with a minimal loaded state
        sm.record_metric("t_elapsed", 1.5)
        sm.record_error("t", "boom", recoverable=False)
        assert sm.get_metrics()["t_elapsed"] == 1.5
