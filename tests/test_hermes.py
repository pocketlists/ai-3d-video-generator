"""Tests for Hermes Agent and Telegram escalation."""
import os
import pytest
from unittest.mock import patch, MagicMock

from controller.hermes import HermesAgent
from controller.telegram_escalation import TelegramEscalation
from controller.state_manager import StateManager


def test_telegram_escalation_disabled_without_config():
    escalation = TelegramEscalation({})
    assert not escalation.enabled


def test_telegram_escalation_enabled_with_config():
    escalation = TelegramEscalation({
        "telegram_bot_token": "test_token",
        "telegram_channel_id": "test_channel"
    })
    assert escalation.enabled


def test_state_manager_resumable(tmp_path):
    sm = StateManager(run_id="test_resume", state_dir=str(tmp_path))
    sm.set_stage_status("receive_request", "completed")
    sm.set_stage_status("ai_planning", "completed")
    sm.set_stage_status("script_breakdown", "completed")
    sm.set_stage_status("asset_collection", "running")

    resume = sm.get_resume_point()
    assert resume == "asset_collection"


def test_state_manager_waiting_for_response(tmp_path):
    sm = StateManager(run_id="test_wait", state_dir=str(tmp_path))
    sm.set_stage_status("ai_planning", "WAITING_FOR_EXTERNAL_RESPONSE", {
        "error": "Gemini API failed"
    })
    assert sm.is_stage_waiting("ai_planning")
    assert not sm.is_stage_complete("ai_planning")


def test_state_manager_pending_escalation(tmp_path):
    sm = StateManager(run_id="test_esc", state_dir=str(tmp_path))
    sm.add_pending_escalation("JOB-123", "ai_planning", "API failed", message_id=456)
    assert sm.has_pending_escalations()
    assert len(sm.get_pending_escalations()) == 1

    sm.resolve_escalation("JOB-123", "ai_planning", "corrected response")
    assert not sm.has_pending_escalations()


def test_state_manager_valid_states(tmp_path):
    from controller.state_manager import VALID_STATES
    assert "WAITING_FOR_EXTERNAL_RESPONSE" in VALID_STATES
    assert "COMPLETED" in VALID_STATES
    assert "FAILED" in VALID_STATES
    assert "CANCELLED" in VALID_STATES


def test_cpu_monitor_init():
    from utils.cpu_monitor import CPUMonitor
    monitor = CPUMonitor(worker_id=0)
    info = monitor.get_system_info()
    assert "cpu_cores" in info
    assert "cpu_model" in info
    assert "ram_total_gb" in info


def test_cpu_monitor_record_frame():
    from utils.cpu_monitor import CPUMonitor
    monitor = CPUMonitor(worker_id=0)
    metrics = monitor.record_frame(1, 120, 1.5, "BLENDER_EEVEE", "1280x720")
    assert metrics.frame_number == 1
    assert metrics.frame_time_sec == 1.5
    assert metrics.total_frames == 120


def test_asset_validator_glb(tmp_path):
    """Test GLB validation with a fake file."""
    from utils.asset_validator import AssetValidator
    validator = AssetValidator()

    # Create a fake GLB file with magic header
    import struct
    glb_path = tmp_path / "test.glb"
    with open(glb_path, "wb") as f:
        f.write(b"glTF")
        f.write(struct.pack("<I", 2))  # version
        f.write(struct.pack("<I", 100))  # length
        # JSON chunk
        json_data = b'{"meshes":[],"materials":[],"textures":[],"animations":[],"skins":[]}'
        f.write(struct.pack("<I", len(json_data)))
        f.write(b"JSON")
        f.write(json_data)

    result = validator.validate(str(glb_path))
    assert result["format"] == "glb"
    assert result["valid"]


def test_asset_validator_missing_file():
    from utils.asset_validator import AssetValidator
    validator = AssetValidator()
    result = validator.validate("/nonexistent/file.glb")
    assert not result["valid"]
    assert "does not exist" in result["issues"][0]


def test_asset_validator_obj(tmp_path):
    from utils.asset_validator import AssetValidator
    validator = AssetValidator()
    obj_path = tmp_path / "test.obj"
    with open(obj_path, "w") as f:
        f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    result = validator.validate(str(obj_path))
    assert result["valid"]
    assert result["polygon_count"] == 1
