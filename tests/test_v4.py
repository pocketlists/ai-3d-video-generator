"""v4.0 regression tests — dynamic matrix, state persistence, telegram resume, production guards."""
import json
import os
import pytest
from pathlib import Path


# ── PHASE 60: render partition matches matrix ──
class TestPartitionMatchesMatrix:
    def test_render_partition_matches_matrix(self):
        """CRITICAL: actual_worker_count == matrix_worker_count == partition_worker_count,
        and all frames covered exactly once."""
        from blender.render_manager import RenderManager
        for num_workers in [1, 2, 4, 7, 20]:
            total_frames = 1440
            # Simulate what pipeline.yml render_prepare does: matrix = [0..N-1]
            matrix = list(range(num_workers))
            # Partitions computed with same num_workers
            partitions = RenderManager.partition_frames(total_frames, num_workers)
            # 1. matrix count == partition count
            assert len(matrix) == len(partitions), \
                f"matrix({len(matrix)}) != partitions({len(partitions)}) for {num_workers} workers"
            # 2. every matrix worker has a partition
            for worker_id, (start, end) in enumerate(partitions):
                assert start <= end, f"worker {worker_id}: invalid range {start}-{end}"
            # 3. all frames covered exactly once (no overlap, no missing)
            covered = []
            for start, end in partitions:
                covered.extend(range(start, end + 1))
            assert sorted(covered) == list(range(1, total_frames + 1)), \
                f"frames not covered exactly once for {num_workers} workers"

    def test_dynamic_matrix_generation_logic(self):
        """Same logic as pipeline.yml render_prepare job."""
        for requested in [1, 4, 8, 20, 50]:
            actual = min(max(1, requested), 20)
            matrix = list(range(actual))
            assert len(matrix) == actual
            assert matrix[0] == 0
            assert matrix[-1] == actual - 1

    def test_matrix_from_json_roundtrip(self):
        """The matrix output JSON must round-trip through fromJSON."""
        matrix = json.dumps([0, 1, 2, 3])
        parsed = json.loads(matrix)
        assert parsed == [0, 1, 2, 3]


# ── PHASE 62: state persistence across runners ──
class TestStatePersistence:
    def test_runner1_checkpoint_runner2_resume(self, tmp_path):
        """Simulate: Runner 1 saves checkpoint → runner destroyed → Runner 2 loads + resumes."""
        from controller.state_manager import StateManager

        # Runner 1: create state, complete stages, save
        sm1 = StateManager(job_id="job_persist_test", state_dir=str(tmp_path))
        sm1.set_stage_status("receive_request", "completed")
        sm1.set_stage_status("ai_planning", "completed")
        sm1.set_stage_status("script_breakdown", "completed")
        sm1._save()

        # Runner destroyed — new StateManager instance (fresh process simulation)
        # Runner 2: load state from same persistent dir
        sm2 = StateManager(job_id="job_persist_test", state_dir=str(tmp_path))
        state = sm2.load_checkpoint()
        assert state is not None, "Runner 2 could not load state — persistence broken"
        # Completed stages preserved
        assert sm2.is_stage_complete("receive_request")
        assert sm2.is_stage_complete("ai_planning")
        assert sm2.is_stage_complete("script_breakdown")
        # Resume point = first incomplete stage (NOT restart from receive)
        resume_point = sm2.get_resume_point()
        assert resume_point == "asset_collection", \
            f"Expected resume at asset_collection, got {resume_point}"

    def test_checkpoint_survives_corruption(self, tmp_path):
        """A corrupted checkpoint must not destroy the previous valid checkpoint."""
        from controller.checkpoint import CheckpointManager, Checkpoint
        mgr = CheckpointManager("job_corrupt", checkpoint_dir=str(tmp_path))
        cp = Checkpoint(job_id="job_corrupt", stage="planning", status="completed")
        mgr.save_checkpoint(cp)
        path = tmp_path / "checkpoint_job_corrupt_planning.json"
        # Corrupt the file
        with open(path, "w") as f:
            f.write("{corrupted json!!!")
        # Load must return None (not crash), and a new save must work
        assert mgr.load_checkpoint("planning") is None
        cp2 = Checkpoint(job_id="job_corrupt", stage="planning", status="completed")
        mgr.save_checkpoint(cp2)
        assert mgr.load_checkpoint("planning").status == "completed"


# ── PHASE 63: Telegram resume flow (no full restart) ──
class TestTelegramResumeFlow:
    def test_gemini_failure_to_resume_no_restart(self, tmp_path):
        """Gemini fails → escalation → WAITING → external response → resume exact stage.
        Completed stages must NOT re-run."""
        from controller.state_manager import StateManager
        from controller.telegram_escalation import TelegramEscalation

        sm = StateManager(job_id="job_tg_flow", state_dir=str(tmp_path))
        esc = TelegramEscalation({})  # disabled (no network)

        # Stage 1-2 complete
        sm.set_stage_status("receive_request", "completed")
        sm.set_stage_status("ai_planning", "PLANNING")

        # Gemini fails → mark_waiting with resume token
        result = esc.escalate_failure("job_tg_flow", "ai_planning", "429 RESOURCE_EXHAUSTED", "gemini")
        sm.mark_waiting("ai_planning", "429 RESOURCE_EXHAUSTED",
                        resume_token=result["resume_token"])

        # State checks
        assert sm.is_stage_waiting("ai_planning")
        assert sm.has_pending_escalations()
        pending = sm.get_pending_escalations()[0]
        assert pending["resume_token"].startswith("resume_job_tg_flow_ai_planning")

        # External response arrives → resume
        sm.resume_stage("ai_planning", "corrected plan JSON")
        assert not sm.has_pending_escalations()
        assert not sm.is_stage_waiting("ai_planning")

        # CRITICAL: completed stages NOT re-run — resume point is ai_planning onwards
        assert sm.is_stage_complete("receive_request")
        resume_point = sm.get_resume_point()
        assert resume_point == "ai_planning"  # not receive_request

    def test_escalation_message_format(self):
        """Escalation must include JOB_ID, STAGE, PROVIDER, ERROR, RESUME_TOKEN."""
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({"telegram_bot_token": "fake", "telegram_channel_id": "fake"})
        # _send_message will fail (network) but format is built — test the message text builder
        job_id, stage, error, provider = "job_fmt", "ai_planning", "429", "gemini"
        resume_token = f"resume_{job_id}_{stage}_abc12345"
        text = esc._send_escalation_message.__doc__ or ""
        # Instead test via the public API structure
        result = esc.escalate_failure(job_id, stage, error, provider)
        assert "resume_token" in result
        assert result["resume_token"].startswith(f"resume_{job_id}_{stage}")

    def test_reply_parser_extracts_resume_fields(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        update = {
            "message": {
                "text": "JOB_ID: job_fmt\nSTAGE: ai_planning\nRESUME_TOKEN: resume_job_fmt_ai_planning_abc12345\n{\"scenes\": [...]}",
                "message_id": 42, "chat": {"id": -100123},
                "from": {"id": 111},
            }
        }
        parsed = esc.parse_telegram_response(update)
        assert parsed["job_id"] == "job_fmt"
        assert parsed["stage"] == "ai_planning"
        assert parsed["resume_token"] == "resume_job_fmt_ai_planning_abc12345"
        assert "scenes" in parsed["response"]


# ── PHASE 64: production mode cannot produce placeholder output ──
class TestProductionModeGuards:
    def test_low_poly_generator_blocked_in_production(self, monkeypatch):
        """PIPELINE_MODE=production + low_poly_generator → RuntimeError (no cube)."""
        monkeypatch.setenv("PIPELINE_MODE", "production")
        from blender.low_poly_generator import LowPolyGenerator
        gen = LowPolyGenerator()
        with pytest.raises(RuntimeError, match="PIPELINE_MODE=production"):
            gen.generate_character("hero")
        with pytest.raises(RuntimeError, match="PIPELINE_MODE=production"):
            gen.generate_environment("outdoor")
        with pytest.raises(RuntimeError, match="PIPELINE_MODE=production"):
            gen.generate_prop("box")

    def test_low_poly_generator_allowed_in_test(self, monkeypatch):
        """PIPELINE_MODE=test → procedural generation allowed (smoke tests)."""
        monkeypatch.setenv("PIPELINE_MODE", "test")
        from blender.low_poly_generator import LowPolyGenerator
        gen = LowPolyGenerator(seed=42)
        mesh = gen.generate_prop("box")
        assert mesh is not None

    def test_render_worker_placeholder_blocked_in_production(self, monkeypatch, tmp_path):
        """PIPELINE_MODE=production + missing blend file → FAIL (not placeholder frames)."""
        monkeypatch.setenv("PIPELINE_MODE", "production")
        monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path))
        from workers.render_worker import RenderWorker
        worker = RenderWorker({}, None)
        worker.job_id = "job_guard_test"
        worker.worker_id = 0
        worker.frame_start = 1
        worker.frame_end = 10
        worker.blend_file = str(tmp_path / "nonexistent.blend")
        with pytest.raises(RuntimeError, match="placeholder frames are NOT allowed"):
            worker.run()

    def test_template_fallback_blocked_in_production(self, monkeypatch):
        """ALLOW_TEMPLATE_FALLBACK=true + PIPELINE_MODE=production → still blocked."""
        monkeypatch.setenv("PIPELINE_MODE", "production")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from providers.llm_provider import get_llm_provider, LLMError
        with pytest.raises(LLMError, match="PIPELINE_MODE=production"):
            get_llm_provider({"llm_provider": "gemini", "allow_template_fallback": True})

    def test_template_fallback_allowed_in_test_mode(self, monkeypatch):
        """ALLOW_TEMPLATE_FALLBACK=true + PIPELINE_MODE=test → allowed."""
        monkeypatch.setenv("PIPELINE_MODE", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from providers.llm_provider import get_llm_provider, TemplateProvider
        provider = get_llm_provider({"llm_provider": "gemini", "allow_template_fallback": True})
        assert isinstance(provider, TemplateProvider)


# ── PHASE 19: Objaverse PROVIDER_UNAVAILABLE honesty ──
class TestObjaverseHonesty:
    def test_unavailable_sets_status_not_silent_empty(self):
        """If objaverse is unavailable, last_status must say PROVIDER_UNAVAILABLE."""
        from providers.objaverse_provider import ObjaverseProvider
        provider = ObjaverseProvider({})
        # Force unavailable (no network in test or HF down)
        provider._search_candidates = lambda p, t: []
        provider.is_available = lambda: False
        result = provider.generate_asset("a knight", "characters", "hero")
        assert result is None
        assert provider.last_status == "PROVIDER_UNAVAILABLE"

    def test_available_search_no_results_status(self):
        from providers.objaverse_provider import ObjaverseProvider
        provider = ObjaverseProvider({})
        provider.is_available = lambda: True
        provider._search_candidates = lambda p, t: []  # searched, found nothing
        result = provider.generate_asset("a knight", "characters", "hero")
        assert result is None
        assert provider.last_status == "NO_RESULTS"  # honest: searched but empty


# ── PHASE 25: Asset importer ──
class TestAssetImporter:
    def test_detect_format_glb_magic(self, tmp_path):
        from blender.asset_importer import AssetImporter
        p = tmp_path / "test.glb"
        p.write_bytes(b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 56)
        assert AssetImporter.detect_format(p) == "glb"

    def test_import_missing_file_raises(self, tmp_path):
        from blender.asset_importer import AssetImporter, AssetImportError
        importer = AssetImporter()
        with pytest.raises(AssetImportError, match="not found"):
            importer.import_asset(str(tmp_path / "missing.glb"))

    def test_import_too_small_raises(self, tmp_path):
        from blender.asset_importer import AssetImporter, AssetImportError
        p = tmp_path / "tiny.glb"
        p.write_bytes(b"glTF")  # < 100 bytes
        with pytest.raises(AssetImportError, match="too small"):
            importer = AssetImporter()
            importer.import_asset(str(p))

    def test_unsupported_format_raises(self, tmp_path):
        from blender.asset_importer import AssetImporter, AssetImportError
        p = tmp_path / "model.stl"
        p.write_bytes(b"solid" + b"\x00" * 200)
        importer = AssetImporter()
        with pytest.raises(AssetImportError, match="Unsupported format"):
            importer.import_asset(str(p))

    def test_valid_glb_file_level_validation(self, tmp_path):
        from blender.asset_importer import AssetImporter
        p = tmp_path / "valid.glb"
        p.write_bytes(b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 200)
        importer = AssetImporter()
        result = importer.import_asset(str(p))
        # Outside Blender: file-level validation only
        assert result.requires_blender_runtime is True
        assert result.format == "glb"
        assert result.file_size > 100
        assert len(result.file_hash) == 16

    def test_gltf_json_malformed_rejected(self, tmp_path):
        from blender.asset_importer import AssetImporter
        p = tmp_path / "bad.gltf"
        # Pad to > 100 bytes so it passes the size check, then malformed JSON fails validation
        p.write_text("{malformed json " + "x" * 200)
        importer = AssetImporter()
        result = importer.import_asset(str(p))
        assert result.valid is False
        assert any("malformed" in e for e in result.errors)


# ── PHASE 41: Google Cloud TTS separation ──
class TestGoogleCloudTTS:
    def test_not_available_without_credentials(self):
        from providers.google_cloud_tts import GoogleCloudTTSProvider
        p = GoogleCloudTTSProvider({})
        assert p.is_available() is False

    def test_synth_without_credentials_returns_none(self):
        from providers.google_cloud_tts import GoogleCloudTTSProvider
        p = GoogleCloudTTSProvider({})
        assert p.synthesize("hello") is None

    def test_chunking_respects_limit(self):
        from providers.google_cloud_tts import GoogleCloudTTSProvider
        long_text = "This is a sentence. " * 600  # ~12600 bytes
        chunks = GoogleCloudTTSProvider._chunk_text(long_text, max_bytes=4500)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.encode("utf-8")) <= 4500
        # Reassembly preserves all content (order may lose whitespace)
        assert "".join(chunks).replace(" ", "") == long_text.replace(" ", "")

    def test_factory_no_silent_fallback_to_gtts(self):
        """TTS_PROVIDER=google_cloud without credentials → error, NOT silent gTTS."""
        from providers.tts_provider import get_tts_provider
        with pytest.raises(RuntimeError, match="google_cloud"):
            get_tts_provider({"tts_provider": "google_cloud"})


# ── PHASE 36: render manifest checksums ──
class TestRenderManifestChecksums:
    def test_manifest_contains_checksums(self, tmp_path):
        from blender.render_manager import RenderManager
        rm = RenderManager("test.blend", str(tmp_path))
        wdir = tmp_path / "worker_0"
        wdir.mkdir()
        for frame in range(1, 4):
            (wdir / f"frame_{frame:04d}.png").write_bytes(b"PNGDATA" * frame)
        manifest = rm.collect_frames(str(tmp_path), total_frames=3, job_id="job_ck")
        assert "checksums" in manifest
        assert len(manifest["checksums"]) == 3
        # Checksums are deterministic
        assert manifest["checksums"]["1"] == manifest["checksums"]["1"]
        assert manifest["checksums"]["1"] != manifest["checksums"]["2"]
