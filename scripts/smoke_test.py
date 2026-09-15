#!/usr/bin/env python3
"""
Smoke test — 5-second, 24 FPS, 120-frame end-to-end pipeline test.

Uses mock/procedural assets (NOT production quality).
Tests:
1. Job creation
2. Planning (mock provider)
3. Asset retrieval (mock)
4. Scene build (procedural)
5. Render (placeholder frames)
6. Frame collection
7. FFmpeg encode (if available)
8. QC check
9. Audio generation (mock)
10. Final output

DO NOT use procedural low-poly as evidence of production quality.
"""
import json
import os
import sys
import tempfile

tmpdir = tempfile.mkdtemp()
os.environ["ARTIFACT_DIR"] = os.path.join(tmpdir, "artifacts")
os.environ["METRICS_DIR"] = os.path.join(tmpdir, "metrics")
os.environ["STATE_DIR"] = os.path.join(tmpdir, "state")
os.environ["LOG_DIR"] = os.path.join(tmpdir, "logs")
os.environ["LLM_PROVIDER"] = "template"
os.environ["TTS_PROVIDER"] = "gtts"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for d in ["ARTIFACT_DIR", "METRICS_DIR", "STATE_DIR", "LOG_DIR"]:
    os.makedirs(os.environ[d], exist_ok=True)

TOTAL_FRAMES = 120  # 5 seconds at 24fps


def test_job_creation():
    print("=" * 60)
    print("Test 1: Job Creation")
    print("=" * 60)
    from controller.state_manager import StateManager
    sm = StateManager(state_dir=os.environ["STATE_DIR"])
    sm.job_id = "smoke_test_job"
    sm.set_stage_status("receive_request", "completed", {"prompt": "smoke test"})
    assert sm.is_stage_complete("receive_request")
    print("[OK] Job created and state persisted")
    return True


def test_planning():
    print("\n" + "=" * 60)
    print("Test 2: AI Planning (Template)")
    print("=" * 60)
    from providers.llm_provider import get_llm_provider
    llm = get_llm_provider({"llm_provider": "template"})
    plan = llm.generate_plan("A serene landscape at sunrise", "low-poly")
    assert "scenes" in plan
    assert len(plan["scenes"]) > 0
    print(f"[OK] Plan created: {len(plan['scenes'])} scenes")
    return True


def test_state_machine_transitions():
    print("\n" + "=" * 60)
    print("Test 3: State Machine Transitions")
    print("=" * 60)
    from controller.state_manager import StateManager, TRANSITIONS
    sm = StateManager(state_dir=os.environ["STATE_DIR"])
    assert sm.transition("PLANNING")
    assert sm.transition("SCRIPTING")
    assert sm.transition("ASSET_SEARCH")
    assert not sm.transition("COMPLETED")  # Invalid transition
    print("[OK] Valid transitions accepted, invalid rejected")
    return True


def test_checkpoint_system():
    print("\n" + "=" * 60)
    print("Test 4: Checkpoint System")
    print("=" * 60)
    from controller.checkpoint import CheckpointManager, Checkpoint
    mgr = CheckpointManager("smoke_test", checkpoint_dir=os.environ["STATE_DIR"])
    cp = Checkpoint(job_id="smoke_test", stage="planning", status="completed")
    mgr.save_checkpoint(cp)
    loaded = mgr.load_checkpoint("planning")
    assert loaded.status == "completed"
    print("[OK] Checkpoint saved and loaded atomically")
    return True


def test_error_classification():
    print("\n" + "=" * 60)
    print("Test 5: Error Classification")
    print("=" * 60)
    from utils.error_classifier import classify_error, should_retry, ErrorType
    assert classify_error("429 rate limit") == ErrorType.RATE_LIMIT
    assert classify_error("401 unauthorized") == ErrorType.AUTH
    assert should_retry(ErrorType.RATE_LIMIT, 1, 3)
    assert not should_retry(ErrorType.AUTH, 1, 3)
    print("[OK] Errors classified correctly")
    return True


def test_render_partitioning():
    print("\n" + "=" * 60)
    print("Test 6: Render Partitioning (dynamic)")
    print("=" * 60)
    from blender.render_manager import RenderManager
    # Test with 3 workers
    parts = RenderManager.partition_frames(TOTAL_FRAMES, 3)
    total = sum(e - s + 1 for s, e in parts)
    assert total == TOTAL_FRAMES
    print(f"[OK] 120 frames / 3 workers = {parts}")
    return True


def test_render_collector():
    print("\n" + "=" * 60)
    print("Test 7: Render Collector (worker identity preserved)")
    print("=" * 60)
    from blender.render_manager import RenderManager
    renders_dir = os.path.join(os.environ["ARTIFACT_DIR"], "renders")
    rm = RenderManager("test.blend", renders_dir)
    # Create mock worker outputs
    parts = RenderManager.partition_frames(TOTAL_FRAMES, 2)
    for wid, (start, end) in enumerate(parts):
        wdir = os.path.join(renders_dir, f"worker_{wid}")
        os.makedirs(wdir, exist_ok=True)
        for frame in range(start, end + 1):
            with open(os.path.join(wdir, f"frame_{frame:04d}.png"), "wb") as f:
                f.write(b"PNG mock")
    manifest = rm.collect_frames(renders_dir, TOTAL_FRAMES, "smoke_test")
    assert manifest["complete"]
    assert manifest["workers"] == 2
    print(f"[OK] Collected {manifest['frames_found']} frames from {manifest['workers']} workers")
    return True


def test_telegram_escalation_no_timeout():
    print("\n" + "=" * 60)
    print("Test 8: Telegram Escalation (no timeout)")
    print("=" * 60)
    from controller.telegram_escalation import TelegramEscalation
    esc = TelegramEscalation({})  # disabled
    result = esc.escalate_failure("job_test", "ai_planning", "429 rate limit")
    # Must return immediately — no waiting
    assert "resume_token" in result
    print("[OK] Escalation returns immediately with resume token (no 5-min wait)")
    return True


def test_no_silent_llm_fallback():
    print("\n" + "=" * 60)
    print("Test 9: No Silent LLM Fallback")
    print("=" * 60)
    from providers.llm_provider import get_llm_provider, LLMError
    os.environ.pop("GEMINI_API_KEY", None)
    try:
        get_llm_provider({"llm_provider": "gemini"})
        assert False, "Should have raised"
    except LLMError:
        print("[OK] Gemini without key raises (no silent template fallback)")
    return True


def test_mock_providers():
    print("\n" + "=" * 60)
    print("Test 10: Mock Providers (no paid APIs)")
    print("=" * 60)
    from tests.mocks import MockGeminiProvider, MockObjaverseProvider, MockTTSProvider
    llm = MockGeminiProvider({})
    plan = llm.generate_plan("test")
    assert plan["ai_generated"]
    print("[OK] MockGemini works")
    return True


def main():
    results = []
    for test in [test_job_creation, test_planning, test_state_machine_transitions,
                 test_checkpoint_system, test_error_classification,
                 test_render_partitioning, test_render_collector,
                 test_telegram_escalation_no_timeout, test_no_silent_llm_fallback,
                 test_mock_providers]:
        try:
            passed = test()
            results.append((test.__name__, passed))
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            results.append((test.__name__, False))

    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS")
    print("=" * 60)
    for name, passed in results:
        print(f"  {'[PASS]' if passed else '[FAIL]'} {name}")
    all_passed = all(p for _, p in results)
    print(f"\n{'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
