#!/usr/bin/env python3
"""
Smoke test — runs the full pipeline locally with minimal settings.

Validates that all stages can execute end-to-end without external
dependencies (Blender, FFmpeg, Telegram, AI APIs).
"""
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

# Create directories
for d in ["ARTIFACT_DIR", "METRICS_DIR", "STATE_DIR", "LOG_DIR"]:
    os.makedirs(os.environ[d], exist_ok=True)


def main():
    from controller.orchestrator import Orchestrator

    print("=" * 60)
    print("AI 3D Video Generator — Smoke Test")
    print("=" * 60)
    print(f"Working directory: {tmpdir}")
    print()

    orchestrator = Orchestrator()

    stages = [
        "ai_planning",
        "script_breakdown",
        "asset_collection",
        "characters",
        "environments",
        "props",
        "animation",
        "camera",
        "lighting",
        "voice_tts",
        "music",
        "sfx",
        "lip_sync",
        "blender_assembly",
        "quality_check",
        "ffmpeg_assembly",
        "self_optimize",
    ]

    passed = 0
    failed = 0
    skipped = 0

    for stage in stages:
        print(f"\n{'─' * 40}")
        result = orchestrator.run_stage(stage)
        if result:
            passed += 1
        else:
            # Check if it was skipped due to missing dependencies
            state = orchestrator.state.get_stage_status(stage)
            if state and state.get("data", {}).get("error", "").startswith("No"):
                skipped += 1
                print(f"  (skipped — missing dependency)")
            else:
                failed += 1

    print(f"\n{'=' * 60}")
    print(f"Smoke Test Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"Total: {passed + failed + skipped}/{len(stages)}")
    print("=" * 60)

    # Export state
    state_json = orchestrator.export_state()
    with open(os.path.join(tmpdir, "final_state.json"), "w") as f:
        f.write(state_json)
    print(f"\nFinal state exported to: {tmpdir}/final_state.json")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
