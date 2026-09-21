"""v8 tests: Telegram channel ID auto-detection from the first message."""
import json
import os
from unittest import mock

import pytest


def _message_updates(users):
    """Build getUpdates result: [(from_user_id, chat_id), ...]."""
    result = []
    for uid, chat in users:
        result.append({"update_id": len(result), "message": {
            "message_id": 1, "from": {"id": uid}, "chat": {"id": chat}}})
    return {"ok": True, "result": result}


class TestDiscoverChannelId:
    def test_discovers_from_first_message(self):
        from utils.telegram_client import discover_channel_id
        with mock.patch("urllib.request.urlopen") as uo:
            resp = uo.return_value.__enter__.return_value
            resp.read.return_value = json.dumps(
                _message_updates([(111, -100999)])).encode()
            assert discover_channel_id("tok") == "-100999"

    def test_prefers_allowed_user_chat(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
        from utils.telegram_client import discover_channel_id
        # random user's chat arrives FIRST, allowed user's chat second
        updates = _message_updates([(999, -100111), (42, -100222)])
        with mock.patch("urllib.request.urlopen") as uo:
            resp = uo.return_value.__enter__.return_value
            resp.read.return_value = json.dumps(updates).encode()
            assert discover_channel_id("tok") == "-100222"

    def test_no_updates_returns_none(self):
        from utils.telegram_client import discover_channel_id
        with mock.patch("urllib.request.urlopen") as uo:
            resp = uo.return_value.__enter__.return_value
            resp.read.return_value = json.dumps(
                {"ok": True, "result": []}).encode()
            assert discover_channel_id("tok") is None

    def test_handles_channel_post_updates(self):
        from utils.telegram_client import discover_channel_id
        payload = {"ok": True, "result": [
            {"update_id": 1, "channel_post": {
                "message_id": 1, "chat": {"id": -100777}}}]}
        with mock.patch("urllib.request.urlopen") as uo:
            resp = uo.return_value.__enter__.return_value
            resp.read.return_value = json.dumps(payload).encode()
            assert discover_channel_id("tok") == "-100777"


class TestPersistence:
    def test_detected_id_persisted_and_reused(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        from utils.telegram_client import (
            save_detected_chat_id, load_detected_chat_id)
        save_detected_chat_id("-100555")
        assert load_detected_chat_id() == "-100555"
        assert load_detected_chat_id() == "-100555"  # survives "new run"

    def test_client_uses_persisted_before_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        os.environ.pop("TELEGRAM_CHANNEL_ID", None)
        from utils.telegram_client import save_detected_chat_id, TelegramClient
        save_detected_chat_id("-100persisted")
        client = TelegramClient()
        with mock.patch("utils.telegram_client.discover_channel_id") as disc:
            client._ensure_channel()
            disc.assert_not_called()  # persisted value wins, no API call
            assert client.channel_id == "-100persisted"

    def test_explicit_env_wins_over_persisted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100explicit")
        from utils.telegram_client import save_detected_chat_id, TelegramClient
        save_detected_chat_id("-100persisted")
        client = TelegramClient(bot_token="tok")
        assert client.channel_id == "-100explicit"


class TestEscalationWithoutChannel:
    def test_escalation_enabled_with_token_only(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        os.environ.pop("TELEGRAM_CHANNEL_ID", None)
        from controller.telegram_escalation import TelegramEscalation
        esc = TelegramEscalation({})
        assert esc.enabled is True  # channel resolves lazily now
