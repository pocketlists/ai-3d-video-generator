"""v10 tests: parallel-job state MERGE — fixes 'Dependency not complete'
for stages fed by PARALLEL jobs (animation/lip_sync/assembly/ffmpeg).

Regression: animation needs characters+environments+props, but each parallel
job uploads its own state file; the loader must MERGE them, not pick one.
"""
import json


class TestParallelStateMerge:
    def _write_states(self, art, base_state, parallel):
        """parallel: {stage: timestamp}"""
        import os
        sdir = art / "state"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "base.json").write_text(json.dumps(base_state))
        for stage, ts in parallel.items():
            st = json.loads(json.dumps(base_state))
            st["stages"][stage] = {"status": "completed", "timestamp": ts}
            (sdir / f"{stage}.json").write_text(json.dumps(st))

    def test_animation_dependencies_merge(self, tmp_path, monkeypatch):
        art = tmp_path / "art"
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(tmp_path / "fresh"))
        base = {"job_id": "j", "stages": {
            "receive_request": {"status": "completed", "timestamp": 1},
            "script_breakdown": {"status": "completed", "timestamp": 2}}}
        self._write_states(art, base,
                           {"characters": 3, "environments": 4, "props": 5})
        from core.storage import LocalStateStore
        (tmp_path / "fresh").mkdir()
        store = LocalStateStore(base_dir=str(tmp_path / "fresh"))
        merged = store.load_state("whatever")
        assert merged is not None
        for dep in ("characters", "environments", "props", "script_breakdown"):
            assert merged["stages"][dep]["status"] == "completed"

    def test_lip_sync_dependencies_merge(self, tmp_path, monkeypatch):
        art = tmp_path / "art"
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(tmp_path / "fresh"))
        base = {"job_id": "j", "stages": {}}
        self._write_states(art, base, {"voice_tts": 3, "characters": 4})
        from core.storage import LocalStateStore
        (tmp_path / "fresh").mkdir()
        store = LocalStateStore(base_dir=str(tmp_path / "fresh"))
        merged = store.load_state("x")
        assert merged["stages"]["voice_tts"]["status"] == "completed"
        assert merged["stages"]["characters"]["status"] == "completed"

    def test_latest_timestamp_wins_per_stage(self, tmp_path, monkeypatch):
        art = tmp_path / "art"
        monkeypatch.setenv("ARTIFACT_DIR", str(art))
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("STATE_DIR", str(tmp_path / "fresh"))
        base = {"job_id": "j", "stages": {}}
        self._write_states(art, base, {"characters": 3})
        # a later FAILED write must override the earlier completed
        st = {"job_id": "j", "stages": {
            "characters": {"status": "failed", "timestamp": 9}}}
        (art / "state" / "retry.json").write_text(json.dumps(st))
        from core.storage import LocalStateStore
        (tmp_path / "fresh").mkdir()
        store = LocalStateStore(base_dir=str(tmp_path / "fresh"))
        merged = store.load_state("x")
        assert merged["stages"]["characters"]["status"] == "failed"

    def test_merge_unit(self):
        from core.storage import LocalStateStore
        merged = LocalStateStore._merge_states([
            {"job_id": "j", "stages": {"a": {"status": "completed", "timestamp": 1}},
             "metrics": {"m1": 1}, "errors": []},
            {"job_id": "j", "stages": {"b": {"status": "completed", "timestamp": 2}},
             "metrics": {"m2": 2}, "errors": [{"stage": "b", "error": "e", "timestamp": 1}]},
        ])
        assert set(merged["stages"]) == {"a", "b"}
        assert merged["metrics"] == {"m1": 1, "m2": 2}
        assert len(merged["errors"]) == 1
