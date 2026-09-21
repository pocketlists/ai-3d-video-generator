"""Tests for Telegram client and delivery worker."""
import os
import pytest

from utils.telegram_client import TelegramClient, TelegramError
from workers.telegram_worker import TelegramWorker


def test_telegram_client_missing_token():
    old = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    try:
        with pytest.raises(TelegramError):
            TelegramClient(bot_token="", channel_id="test")
    finally:
        if old:
            os.environ["TELEGRAM_BOT_TOKEN"] = old


def test_telegram_client_missing_channel():
    """Channel ID is auto-detected: init succeeds without it, but sending
    fails with a clear error when nothing can be auto-detected."""
    import tempfile
    old_t = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_c = os.environ.pop("TELEGRAM_CHANNEL_ID", None)
    old_a = os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)
    old_state = os.environ.pop("STATE_DIR", None)
    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["STATE_DIR"] = td  # no persisted chat id
            client = TelegramClient(bot_token="test_token", channel_id="")
            assert client.channel_id == ""  # init OK — lazy resolution
            from unittest import mock
            with mock.patch("utils.telegram_client.discover_channel_id",
                            return_value=None):
                with pytest.raises(TelegramError, match="auto-detected"):
                    client.send_message("hello")
    finally:
        if old_t:
            os.environ["TELEGRAM_BOT_TOKEN"] = old_t
        if old_c:
            os.environ["TELEGRAM_CHANNEL_ID"] = old_c
        if old_a:
            os.environ["TELEGRAM_ALLOWED_USER_IDS"] = old_a
        if old_state:
            os.environ["STATE_DIR"] = old_state
        else:
            os.environ.pop("STATE_DIR", None)


def test_telegram_client_init():
    client = TelegramClient(bot_token="test_token", channel_id="test_channel")
    assert client.bot_token == "test_token"
    assert client.channel_id == "test_channel"


def test_telegram_worker_init():
    worker = TelegramWorker({"prompt": "test"})
    assert worker.stage_name == "telegram_delivery"


def test_telegram_worker_no_video(tmp_path):
    """Worker should return error when no final video exists."""
    os.environ["ARTIFACT_DIR"] = str(tmp_path)
    worker = TelegramWorker({"prompt": "test"})
    result = worker.run()
    assert result["status"] in ("error", "skipped")


def test_telegram_worker_build_summary():
    worker = TelegramWorker({"prompt": "test"})
    qc = {"passed": True, "total_frames": 1440, "estimated_duration_sec": 60.0, "issues": []}
    results = [{"type": "video", "success": True}, {"type": "message", "success": True}]
    summary = worker._build_summary(qc, results)
    assert "Pipeline Summary" in summary
    assert "1440" in summary
    assert "60" in summary
