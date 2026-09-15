"""v3.0 regression tests — state machine, checkpoint, resume, error classification, partitioning."""
import json
import os
import pytest
import tempfile
from pathlib import Path

# ── State machine tests ──
class TestStateMachine:
    def test_valid_transition(self, tmp_path):
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        assert sm.transition("PLANNING") is True

    def test_invalid_transition_skips(self, tmp_path):
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        # RECEIVED → COMPLETED is invalid (must go through pipeline)
        assert sm.transition("COMPLETED") is False

    def test_can_transition(self):
        from controller.state_manager import TRANSITIONS
        assert "SCRIPTING" in TRANSITIONS["PLANNING"]
        assert "COMPLETED" not in TRANSITIONS["RECEIVED"]

    def test_failed_to_waiting(self, tmp_path):
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        sm.transition("PLANNING")
        sm.transition("FAILED")
        assert sm.transition("WAITING_FOR_EXTERNAL_RESPONSE") is True

    def test_waiting_stages(self, tmp_path):
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        sm.set_stage_status("ai_planning", "WAITING_FOR_EXTERNAL_RESPONSE")
        assert sm.is_stage_waiting("ai_planning")
        assert not sm.is_stage_complete("ai_planning")

    def test_resume_stage_clears_escalation(self, tmp_path):
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        sm.mark_waiting("ai_planning", "test error", resume_token="tok123")
        assert sm.has_pending_escalations()
        sm.resume_stage("ai_planning", "corrected response")
        assert not sm.has_pending_escalations()

    def test_can_resume_meaningful(self, tmp_path):
        """can_resume() must actually check stage completion (was broken in v2)."""
        from controller.state_manager import StateManager
        sm = StateManager(state_dir=str(tmp_path))
        # No stages completed — first incomplete stage is receive_request
        assert sm.can_resume() is True  # can resume from beginning
        point = sm.get_resume_point()
        assert point is not None  # must return a real stage


# ── Checkpoint tests ──
class TestCheckpoint:
    def test_checkpoint_save_load(self, tmp_path):
        from controller.checkpoint import CheckpointManager, Checkpoint
        mgr = CheckpointManager("job_test", checkpoint_dir=str(tmp_path))
        cp = Checkpoint(job_id="job_test", stage="planning", status="completed",
                        input_hash="abc123", output_files=["/tmp/plan.json"])
        mgr.save_checkpoint(cp)
        loaded = mgr.load_checkpoint("planning")
        assert loaded is not None
        assert loaded.status == "completed"
        assert loaded.input_hash == "abc123"

    def test_checkpoint_atomicity(self, tmp_path):
        from controller.checkpoint import CheckpointManager, Checkpoint
        mgr = CheckpointManager("job_test", checkpoint_dir=str(tmp_path))
        cp = Checkpoint(job_id="job_test", stage="rendering", status="completed")
        path = mgr.save_checkpoint(cp)
        # No temp files left behind
        tmp_files = list(Path(tmp_path).glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_compute_hash(self):
        from controller.checkpoint import CheckpointManager
        h1 = CheckpointManager.compute_hash({"a": 1})
        h2 = CheckpointManager.compute_hash({"a": 1})
        h3 = CheckpointManager.compute_hash({"a": 2})
        assert h1 == h2
        assert h1 != h3


# ── Storage tests ──
class TestStorage:
    def test_local_state_store(self, tmp_path):
        from core.storage import LocalStateStore
        store = LocalStateStore(base_dir=str(tmp_path))
        state = {"job_id": "job1", "status": "RUNNING"}
        ref = store.save_state("job1", state)
        loaded = store.load_state("job1")
        assert loaded["job_id"] == "job1"
        assert "job1" in store.list_jobs()

    def test_artifact_state_store(self, tmp_path):
        from core.storage import GitHubArtifactStateStore
        store = GitHubArtifactStateStore(base_dir=str(tmp_path))
        store.save_state("job2", {"status": "PLANNING"})
        loaded = store.load_state("job2")
        assert loaded["status"] == "PLANNING"


# ── Error classifier tests ──
class TestErrorClassifier:
    def test_rate_limit(self):
        from utils.error_classifier import classify_error, ErrorType
        assert classify_error("429 RESOURCE_EXHAUSTED") == ErrorType.RATE_LIMIT
        assert classify_error("Too many requests") == ErrorType.RATE_LIMIT

    def test_auth(self):
        from utils.error_classifier import classify_error, ErrorType
        assert classify_error("401 unauthorized") == ErrorType.AUTH
        assert classify_error("Invalid API key") == ErrorType.AUTH

    def test_transient(self):
        from utils.error_classifier import classify_error, ErrorType
        assert classify_error("Connection timeout") == ErrorType.TRANSIENT

    def test_should_retry(self):
        from utils.error_classifier import should_retry, ErrorType
        assert should_retry(ErrorType.RATE_LIMIT, 1, 3) is True
        assert should_retry(ErrorType.AUTH, 1, 3) is False
        assert should_retry(ErrorType.RATE_LIMIT, 3, 3) is False

    def test_should_escalate(self):
        from utils.error_classifier import should_escalate, ErrorType
        assert should_escalate(ErrorType.AUTH) is True
        assert should_escalate(ErrorType.TRANSIENT, attempts_exhausted=True) is True


# ── LLM provider tests (no silent fallback) ──
class TestLLMProvider:
    def test_no_silent_fallback_gemini(self):
        from providers.llm_provider import get_llm_provider, LLMError
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(LLMError, match="GEMINI_API_KEY"):
            get_llm_provider({"llm_provider": "gemini"})

    def test_fallback_only_when_allowed(self):
        from providers.llm_provider import get_llm_provider, TemplateProvider
        os.environ.pop("GEMINI_API_KEY", None)
        provider = get_llm_provider({"llm_provider": "gemini", "allow_template_fallback": True})
        assert isinstance(provider, TemplateProvider)

    def test_template_when_configured(self):
        from providers.llm_provider import get_llm_provider, TemplateProvider
        assert isinstance(get_llm_provider({"llm_provider": "template"}), TemplateProvider)

    def test_style_aware_prompt(self):
        from providers.llm_provider import GeminiProvider
        provider = GeminiProvider({"gemini_api_key": "test"})
        prompt = provider._build_system_prompt("anime")
        assert "anime" in prompt

    def test_robust_json_extraction(self):
        from providers.llm_provider import GeminiProvider
        provider = GeminiProvider({"gemini_api_key": "test"})
        # JSON with surrounding text
        text = 'Here is your plan:\n{"title": "test", "scenes": [{"id": 1}]}\nDone!'
        result = provider._parse_json_response(text)
        assert result["title"] == "test"

    def test_plan_validation_rejects_empty(self):
        from providers.llm_provider import GeminiProvider, LLMError
        provider = GeminiProvider({"gemini_api_key": "test"})
        with pytest.raises(LLMError, match="empty scenes"):
            provider._validate_plan({"scenes": []})


# ── Telegram escalation tests ──
class TestTelegramEscalation:
    def test_disabled_without_config(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        assert not esc.enabled
        result = esc.escalate_failure("job1", "planning", "test error")
        assert result["escalated"] is False
        assert "resume_token" in result

    def test_resume_token_format(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({"telegram_bot_token": "tok", "telegram_channel_id": "ch"})
        # _send_message will fail (no network) but token is still returned
        result = esc.escalate_failure("job1", "planning", "test error")
        assert result["resume_token"].startswith("resume_job1_planning_")

    def test_parse_telegram_response(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        update = {"message": {"text": "JOB_ID: job123\nRESUME_TOKEN: resume_abc\nhere is the plan"}}
        result = esc.parse_telegram_response(update)
        assert result["job_id"] == "job123"
        assert result["resume_token"] == "resume_abc"

    def test_parse_channel_post(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        update = {"channel_post": {"text": "JOB_ID: job123\nSTAGE: ai_planning"}}
        result = esc.parse_telegram_response(update)
        assert result is not None
        assert result["stage"] == "ai_planning"

    def test_unauthorized_user_rejected(self):
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        esc.allowed_user_ids = ["12345"]
        update = {"message": {"text": "JOB_ID: job123", "from": {"id": 99999}}}
        assert esc.parse_telegram_response(update) is None


# ── Render partitioning tests ──
class TestRenderPartition:
    def test_partition_1440_20(self):
        from blender.render_manager import RenderManager
        parts = RenderManager.partition_frames(1440, 20)
        assert len(parts) == 20
        assert parts[0] == (1, 72)
        assert parts[19] == (1369, 1440)
        # No overlap
        for i in range(1, len(parts)):
            assert parts[i][0] == parts[i-1][1] + 1

    def test_partition_1440_7(self):
        from blender.render_manager import RenderManager
        parts = RenderManager.partition_frames(1440, 7)
        total = sum(e - s + 1 for s, e in parts)
        assert total == 1440

    def test_partition_uneven(self):
        from blender.render_manager import RenderManager
        parts = RenderManager.partition_frames(100, 3)
        total = sum(e - s + 1 for s, e in parts)
        assert total == 100
        # Balanced: 34, 33, 33
        assert parts[0] == (1, 34)

    def test_partition_single_worker(self):
        from blender.render_manager import RenderManager
        parts = RenderManager.partition_frames(100, 1)
        assert parts == [(1, 100)]


# ── Render collector tests ──
class TestRenderCollector:
    def test_collector_preserves_worker_identity(self, tmp_path):
        from blender.render_manager import RenderManager
        rm = RenderManager("test.blend", str(tmp_path))
        renders = tmp_path
        # Create worker dirs with frames
        for wid in range(2):
            wdir = renders / f"worker_{wid}"
            wdir.mkdir(parents=True, exist_ok=True)
            for frame in range(1 + wid*5, 6 + wid*5):
                (wdir / f"frame_{frame:04d}.png").write_bytes(b"png")

        manifest = rm.collect_frames(str(renders), total_frames=10, job_id="job_test")
        assert manifest["complete"] is True
        assert manifest["workers"] == 2
        assert manifest["frames_found"] == 10
        # Frames reference their ORIGINAL worker dirs
        assert "worker_0" in manifest["frames"]["1"]
        assert "worker_1" in manifest["frames"]["6"]

    def test_collector_detects_missing(self, tmp_path):
        from blender.render_manager import RenderManager
        rm = RenderManager("test.blend", str(tmp_path))
        wdir = tmp_path / "worker_0"
        wdir.mkdir()
        for frame in [1, 2, 4]:  # frame 3 missing
            (wdir / f"frame_{frame:04d}.png").write_bytes(b"png")
        manifest = rm.collect_frames(str(tmp_path), total_frames=4)
        assert not manifest["complete"]
        assert 3 in manifest["missing_frames"]

    def test_collector_detects_duplicates(self, tmp_path):
        from blender.render_manager import RenderManager
        rm = RenderManager("test.blend", str(tmp_path))
        for wid in range(2):
            wdir = tmp_path / f"worker_{wid}"
            wdir.mkdir()
            (wdir / "frame_0001.png").write_bytes(b"png")  # duplicate frame 1
        manifest = rm.collect_frames(str(tmp_path), total_frames=1)
        assert 1 in manifest["duplicates"]


# ── FFmpeg worker tests ──
class TestFFmpegWorker:
    def test_raises_on_missing_manifest(self, tmp_path):
        from workers.ffmpeg_worker import FFmpegWorker, FFmpegError
        worker = FFmpegWorker({}, None)
        os.environ["ARTIFACT_DIR"] = str(tmp_path)
        with pytest.raises(FFmpegError, match="render_manifest.json not found"):
            worker.run()

    def test_raises_on_missing_frames(self, tmp_path):
        from workers.ffmpeg_worker import FFmpegWorker, FFmpegError
        os.environ["ARTIFACT_DIR"] = str(tmp_path)
        renders = tmp_path / "renders"
        renders.mkdir()
        manifest = {"total_frames": 10, "frames": {}, "missing_frames": [5, 6],
                    "duplicates": [], "workers": 1}
        with open(renders / "render_manifest.json", "w") as f:
            json.dump(manifest, f)
        worker = FFmpegWorker({}, None)
        with pytest.raises(FFmpegError, match="frames missing"):
            worker.run()


# ── Mock provider tests ──
class TestMocks:
    def test_mock_gemini(self):
        from tests.mocks import MockGeminiProvider
        provider = MockGeminiProvider({})
        plan = provider.generate_plan("test prompt")
        assert plan["provider"] == "gemini"
        assert plan["ai_generated"] is True
        assert len(plan["scenes"]) > 0

    def test_mock_failing_gemini(self):
        from tests.mocks import MockFailingGeminiProvider
        from providers.llm_provider import LLMError
        provider = MockFailingGeminiProvider({})
        with pytest.raises(LLMError, match="429"):
            provider.generate_plan("test")

    def test_mock_objaverse(self, tmp_path):
        from tests.mocks import MockObjaverseProvider
        provider = MockObjaverseProvider({"asset_cache_dir": str(tmp_path)})
        asset = provider.generate_asset("a knight", "characters", "hero")
        assert asset is not None
        assert asset.format == "glb"
        assert asset.file_size > 0
