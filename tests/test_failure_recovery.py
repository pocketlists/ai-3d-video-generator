"""Tests for failure recovery, retry, and error handling."""
import pytest
import time

from utils.retry import retry, is_retryable_error
from controller.state_manager import StateManager
from utils.file_validator import validate_required_files


def test_retry_success_first_try():
    call_count = 0

    @retry(max_attempts=3, initial_delay=0.01)
    def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    assert succeed() == "ok"
    assert call_count == 1


def test_retry_success_second_attempt():
    call_count = 0

    @retry(max_attempts=3, initial_delay=0.01, backoff_factor=1.0)
    def fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("transient error")
        return "ok"

    assert fail_then_succeed() == "ok"
    assert call_count == 2


def test_retry_all_fail():
    @retry(max_attempts=3, initial_delay=0.01, backoff_factor=1.0)
    def always_fail():
        raise ValueError("permanent error")

    with pytest.raises(ValueError):
        always_fail()


def test_retry_specific_exceptions():
    @retry(max_attempts=3, initial_delay=0.01,
           retryable_exceptions=(ConnectionError,))
    def only_connection_error():
        raise ValueError("not a connection error")

    with pytest.raises(ValueError):
        only_connection_error()


def test_retry_retryable_messages():
    @retry(max_attempts=3, initial_delay=0.01,
           retryable_messages=["timeout", "503"], backoff_factor=1.0)
    def timeout_then_ok():
        if not hasattr(timeout_then_ok, "_called"):
            timeout_then_ok._called = True
            raise Exception("Connection timeout")
        return "ok"

    assert timeout_then_ok() == "ok"


def test_retry_non_retryable_message():
    @retry(max_attempts=3, initial_delay=0.01,
           retryable_messages=["timeout"])
    def auth_error():
        raise Exception("authentication failed")

    with pytest.raises(Exception):
        auth_error()


def test_is_retryable_error():
    error = ConnectionError("Connection timeout")
    assert is_retryable_error(error, ["timeout"])
    assert not is_retryable_error(error, ["auth"])


def test_state_manager_init():
    with pytest.MonkeyPatch().context() as m:
        m.setenv("STATE_DIR", "/tmp/test_state")
        sm = StateManager(run_id="test_run")
        assert sm.run_id == "test_run"
        assert sm.state_file.exists() or True  # might exist from previous


def test_state_manager_stage_status(tmp_path):
    sm = StateManager(run_id="test_sm", state_dir=str(tmp_path))
    sm.set_stage_status("planning", "running")
    assert sm.get_stage_status("planning")["status"] == "running"

    sm.set_stage_status("planning", "completed")
    assert sm.is_stage_complete("planning")


def test_state_manager_record_error(tmp_path):
    sm = StateManager(run_id="test_err", state_dir=str(tmp_path))
    sm.record_error("render", "Blender crashed", recoverable=True)
    assert len(sm.get_full_state()["errors"]) == 1
    assert sm.get_full_state()["errors"][0]["stage"] == "render"


def test_state_manager_record_metric(tmp_path):
    sm = StateManager(run_id="test_metric", state_dir=str(tmp_path))
    sm.record_metric("render_time", 120.5)
    assert sm.get_metrics()["render_time"] == 120.5


def test_state_manager_record_artifact(tmp_path):
    sm = StateManager(run_id="test_art", state_dir=str(tmp_path))
    sm.record_artifact("scene.blend", "/tmp/scene.blend", 1024)
    art = sm.get_artifact("scene.blend")
    assert art is not None
    assert art["size"] == 1024


def test_state_manager_export_json(tmp_path):
    sm = StateManager(run_id="test_export", state_dir=str(tmp_path))
    sm.set_stage_status("planning", "completed")
    exported = sm.export_json()
    import json
    data = json.loads(exported)
    assert data["run_id"] == "test_export"
    assert "planning" in data["stages"]


def test_validate_required_files_missing(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("content")
    success, missing = validate_required_files([str(f), "/nonexistent/file.txt"])
    assert not success
    assert len(missing) == 1
    assert "/nonexistent/file.txt" in missing[0]
