#!/usr/bin/env python3
"""
Smoke test — end-to-end pipeline test with fake assets.

Tests:
1. Request → Planning → Asset handling → Blender → Render → FFmpeg → Quality check
2. Gemini failure → Telegram escalation → WAIT → simulated reply → resume

Does NOT require expensive AI generation. Uses test/fake assets.
"""
import json
import os
import sys
import tempfile

# Set up environment
tmpdir = tempfile.mkdtemp()
os.environ["ARTIFACT_DIR"] = os.path.join(tmpdir, "artifacts")
os.environ["METRICS_DIR"] = os.path.join(tmpdir, "metrics")
os.environ["STATE_DIR"] = os.path.join(tmpdir, "state")
os.environ["LOG_DIR"] = os.path.join(tmpdir, "logs")
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for d in ["ARTIFACT_DIR", "METRICS_DIR", "STATE_DIR", "LOG_DIR"]:
    os.makedirs(os.environ[d], exist_ok=True)


def test_pipeline_stages():
    """Test that all pipeline stages can execute."""
    from controller.orchestrator import Orchestrator

    print("=" * 60)
    print("Test 1: Pipeline Stage Execution")
    print("=" * 60)

    orchestrator = Orchestrator()
    stages = ["ai_planning", "script_breakdown", "asset_collection", "characters",
              "environments", "props", "animation", "camera", "lighting",
              "voice_tts", "music", "sfx", "lip_sync",
              "blender_assembly", "quality_check", "ffmpeg_assembly", "self_optimize"]

    passed = 0
    failed = 0
    for stage in stages:
        result = orchestrator.run_stage(stage)
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nResult: {passed} passed, {failed} failed out of {len(stages)}")
    return failed == 0


def test_telegram_escalation():
    """Test Telegram escalation flow (without real Telegram)."""
    print("\n" + "=" * 60)
    print("Test 2: Telegram Escalation Flow")
    print("=" * 60)

    from controller.telegram_escalation import TelegramEscalation
    from controller.state_manager import StateManager

    # Escalation should be disabled without Telegram config
    escalation = TelegramEscalation({})
    assert not escalation.enabled
    print("[OK] Escalation disabled without config")

    # State manager should support WAITING_FOR_EXTERNAL_RESPONSE
    sm = StateManager(run_id="test_esc")
    sm.set_stage_status("ai_planning", "WAITING_FOR_EXTERNAL_RESPONSE", {
        "error": "Gemini API failed"
    })
    assert sm.is_stage_waiting("ai_planning")
    print("[OK] State supports WAITING_FOR_EXTERNAL_RESPONSE")

    # Should be able to resolve escalation
    sm.resolve_escalation("test_esc", "ai_planning", "corrected plan")
    assert sm.is_stage_complete("ai_planning")
    print("[OK] Escalation resolution works")

    return True


def test_provider_abstraction():
    """Test that all providers can be initialized."""
    print("\n" + "=" * 60)
    print("Test 3: Provider Abstraction")
    print("=" * 60)

    from providers.llm_provider import get_llm_provider, TemplateProvider
    from providers.tts_provider import get_tts_provider
    from providers.asset_provider import get_asset_provider
    from providers.audio_provider import get_music_provider, get_sfx_provider
    from providers.lip_sync_provider import get_lip_sync_provider

    llm = get_llm_provider({})
    assert isinstance(llm, TemplateProvider)
    print("[OK] LLM provider: TemplateProvider")

    tts = get_tts_provider({"artifact_dir": "/tmp/test"})
    print(f"[OK] TTS provider: {tts.__class__.__name__}")

    asset = get_asset_provider({})
    print(f"[OK] Asset provider: {asset.__class__.__name__}")

    music = get_music_provider({})
    assert music.is_available()
    print(f"[OK] Music provider: {music.__class__.__name__}")

    sfx = get_sfx_provider({})
    assert sfx.is_available()
    print(f"[OK] SFX provider: {sfx.__class__.__name__}")

    lip = get_lip_sync_provider({})
    assert lip.is_available()
    print(f"[OK] LipSync provider: {lip.__class__.__name__}")

    return True


def test_cpu_monitoring():
    """Test CPU monitoring system."""
    print("\n" + "=" * 60)
    print("Test 4: CPU/RAM Monitoring")
    print("=" * 60)

    from utils.cpu_monitor import CPUMonitor

    monitor = CPUMonitor(worker_id=0)
    info = monitor.get_system_info()
    print(f"[OK] System: {info['cpu_cores']} cores, {info['ram_total_gb']}GB RAM")

    # Record a fake frame
    metrics = monitor.record_frame(1, 120, 1.5, "BLENDER_EEVEE", "1280x720")
    print(f"[OK] Frame metrics: {metrics.frame_time_sec}s, CPU {metrics.cpu_percent}%")
    print(f"     Report:\n{metrics.format_report()}")

    summary = monitor.get_summary()
    assert summary["frames_rendered"] == 1
    print(f"[OK] Summary: {summary['frames_rendered']} frames, avg {summary['avg_frame_time_sec']}s")

    return True


def main():
    results = []

    results.append(("Pipeline Stages", test_pipeline_stages()))
    results.append(("Telegram Escalation", test_telegram_escalation()))
    results.append(("Provider Abstraction", test_provider_abstraction()))
    results.append(("CPU Monitoring", test_cpu_monitoring()))

    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS")
    print("=" * 60)
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    all_passed = all(p for _, p in results)
    print(f"\n{'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
