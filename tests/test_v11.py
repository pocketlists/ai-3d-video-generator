"""v11 tests: per-job UNIQUE state filenames — fixes parallel download
collision where multiple artifacts' state files shared ONE name and
overwrote each other on download (losing all but the last job's stage).
"""
import json
import os
import shutil


class TestUniqueStateFilenames:
    def _run_parallel_job(self, monkeypatch, tmp_path, job_key, stage, base_state):
        """Simulate one parallel CI job: fresh runner, base artifact
        present, run orchestrator, return its artifact dir."""
        job_dir = tmp_path / f"job_{job_key}"
        art = job_dir / "art"
        (art / "state").mkdir(parents=True)
        (art / "state" / "base.json").write_text(json.dumps(base_state))
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("STATE_DIR", str(job_dir / "state"))
        monkeypatch.setenv("GITHUB_JOB", job_key)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        from controller.orchestrator import Orchestrator
        assert Orchestrator().run_stage(stage)
        return art

    def test_no_collision_after_multi_artifact_download(self, tmp_path, monkeypatch):
        """characters+environments+props upload distinct state files;
        animation downloads all three — merge must see every stage."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_BACKEND", "local")
        monkeypatch.setenv("PIPELINE_MODE", "test")
        monkeypatch.setenv("GITHUB_RUN_ID", "99")
        monkeypatch.delenv("JOB_ID", raising=False)

        base = {"job_id": "99", "stages": {
            "script_breakdown": {"status": "completed", "timestamp": 2}},
            "artifacts": {}, "errors": [], "metrics": {}}

        uploads = {}
        for jk, st in [("characters", "characters"),
                       ("environments", "environments"),
                       ("props", "props")]:
            uploads[jk] = self._run_parallel_job(monkeypatch, tmp_path, jk, st, base)

        # animation: downloads all 3 artifacts into ONE dir
        anim = tmp_path / "anim"
        art = anim / "art"
        (art / "state").mkdir(parents=True)
        for jk in ("characters", "environments", "props"):
            shutil.copytree(uploads[jk], art, dirs_exist_ok=True)

        state_files = list((art / "state").glob("*.json"))
        # distinct per-job filenames survive the download (no overwrite)
        names = sorted(p.name for p in state_files)
        assert len(state_files) == 4, f"expected base+3 job files, got {names}"
        assert len(names) == len(set(names))

        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("STATE_DIR", str(anim / "fresh"))
        (anim / "fresh").mkdir()
        from controller.state_manager import StateManager
        sm = StateManager()
        for dep in ("characters", "environments", "props", "script_breakdown"):
            assert sm.is_stage_complete(dep), f"collision: {dep} missing"

    def test_mirror_uses_github_job_suffix(self, tmp_path, monkeypatch):
        art = tmp_path / "art"
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_JOB", "characters")
        from core.storage import LocalStateStore
        (tmp_path / "st").mkdir()
        store = LocalStateStore(base_dir=str(tmp_path / "st"))
        store.save_state("run1", {"job_id": "run1", "stages": {}})
        assert (art / "state" / "run1_characters.json").exists()
