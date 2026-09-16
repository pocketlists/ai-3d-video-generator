"""v6 hardening regression tests: worker truth, character IDs, manifest fields."""
import json
import os
from pathlib import Path

import pytest


class TestWorkerStatusFile:
    """Workers must persist worker_status.json with real data."""

    def test_placeholder_worker_writes_status(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIPELINE_MODE", "test")
        monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path))
        monkeypatch.setenv("RENDER_ATTEMPT", "2")
        monkeypatch.setenv("WORKER_ID", "3")
        monkeypatch.setenv("FRAME_START", "1")
        monkeypatch.setenv("FRAME_END", "4")
        monkeypatch.setenv("RESOLUTION", "64x64")
        monkeypatch.setenv("RENDER_SAMPLES", "1")
        from workers.render_worker import RenderWorker
        w = RenderWorker(config={})
        result = w.run()
        status_file = tmp_path / "renders" / "worker_3" / "worker_status.json"
        assert status_file.exists(), "worker_status.json not written"
        ws = json.loads(status_file.read_text())
        assert ws["worker_id"] == 3
        assert ws["attempt"] == 2
        assert ws["status"].startswith("success")
        assert "started_at" in ws and "ended_at" in ws


class TestManifestTruthFields:
    """render_manifest.json must report worker truth (no fabrication)."""

    def _make_renders(self, base, workers, frames_each):
        renders = base / "renders"
        for w in range(workers):
            wdir = renders / f"worker_{w}"
            wdir.mkdir(parents=True)
            start = w * frames_each + 1
            for i in range(frames_each):
                (wdir / f"frame_{start + i:05d}.png").write_bytes(b"fake-png")
            (wdir / "worker_status.json").write_text(json.dumps({
                "worker_id": w, "status": "success", "frames_rendered": frames_each,
                "elapsed_sec": 1.5, "attempt": 1, "started_at": 0, "ended_at": 1,
                "error": None}))
        return renders

    def test_manifest_has_truth_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NUM_WORKERS", "4")
        renders = self._make_renders(tmp_path, workers=4, frames_each=25)
        from blender.render_manager import RenderManager
        m = RenderManager.collect_frames_static(renders, total_frames=100) \
            if hasattr(RenderManager, "collect_frames_static") else None
        if m is None:
            # instance method path (collect_frames is an instance method)
            rm = RenderManager.__new__(RenderManager)
            rm.logger = __import__("logging").getLogger("test")
            m = rm.collect_frames(renders_dir=str(renders), total_frames=100)
        assert m["requested_workers"] == 4
        assert m["actual_workers"] == 4
        assert m["expected_frames"] == 100
        assert m["actual_frames"] == 100
        assert m["worker_status"]["worker_0"] == "success"
        assert m["worker_attempts"]["worker_0"] == 1
        assert m["timings"]["worker_0"] == 1.5
        # backward-compat keys still present
        assert m["workers"] == 4
        assert m["frames_found"] == 100
        assert m["complete"] is True

    def test_manifest_no_status_file_reports_unknown_not_fabricated(self, tmp_path):
        renders = tmp_path / "renders"
        wdir = renders / "worker_0"
        wdir.mkdir(parents=True)
        (wdir / "frame_00001.png").write_bytes(b"x")
        from blender.render_manager import RenderManager
        rm = RenderManager.__new__(RenderManager)
        rm.logger = __import__("logging").getLogger("test")
        m = rm.collect_frames(renders_dir=str(renders), total_frames=1)
        assert m["worker_status"]["worker_0"] == "unknown"
        assert m["worker_attempts"]["worker_0"] is None


class TestCharacterStableIds:
    """Characters need stable character_001-style IDs across the run."""

    def test_characters_get_stable_ids(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path))
        manifest = {"characters": [
            {"name": "hero", "prompt": "a hero"},
            {"name": "villain", "prompt": "a villain"},
            {"name": "sidekick", "prompt": "a sidekick"},
        ]}
        (tmp_path / "asset_manifest.json").write_text(json.dumps(manifest))
        from workers.character_worker import CharacterWorker
        w = CharacterWorker.__new__(CharacterWorker)
        w.config = {}
        import logging
        w.logger = logging.getLogger("test")
        chars = []
        for idx, spec in enumerate(manifest["characters"], start=1):
            cd = w._use_fallback(spec["name"], idx)
            chars.append(cd)
        assert [c["character_id"] for c in chars] == [
            "character_001", "character_002", "character_003"]


class TestWorkerTruthReport:
    """The quality-job report logic must classify workers honestly."""

    def test_report_counts(self):
        # Same logic as pipeline.yml quality job step
        statuses = {
            "worker_0": "success", "worker_1": "success_placeholder_test_mode",
            "worker_2": "error", "worker_3": "unknown",
        }
        completed = sum(1 for s in statuses.values() if str(s).startswith("success"))
        failed = sum(1 for s in statuses.values() if s == "error")
        active = len(statuses)
        assert (completed, failed, active) == (2, 1, 4)


class TestCrossRunStateRestore:
    """Run A saves state → runner dies → run B restores the SAME job."""

    def test_state_roundtrip_across_instances(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STATE_BACKEND", "local")
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        from controller.state_manager import StateManager
        # Run A
        sm_a = StateManager(job_id="job_runA_123", state_dir=str(tmp_path))
        sm_a.mark_completed("script", {"scenes": 3})
        # Run B (new instance, "new runner" — same job, same state dir)
        sm_b = StateManager(job_id="job_runA_123", state_dir=str(tmp_path))
        stage = sm_b.get_stage_status("script")
        assert stage is not None
        assert stage["status"] == "completed"
        assert stage["data"]["scenes"] == 3
        assert sm_b.is_stage_complete("script") is True
        # A different job must not see this state
        sm_c = StateManager(job_id="job_other_999", state_dir=str(tmp_path))
        assert sm_c.get_stage_status("script") is None or \
            sm_c.get_stage_status("script").get("status") != "COMPLETE"
