"""
Telegram client — sends messages, photos, documents, and videos to Telegram.

Uses the Telegram Bot API for delivery of pipeline progress updates,
intermediate assets, and the final generated video.
"""
import json
import logging
import os
from typing import Optional, Dict, Any
from pathlib import Path

from utils.retry import retry

logger = logging.getLogger(__name__)


class TelegramError(Exception):
    """Raised when a Telegram API call fails."""


def _chat_id_store_path() -> Path:
    """Where the auto-detected chat/channel ID is persisted."""
    state_dir = os.environ.get("STATE_DIR", "/tmp/pipeline_state")
    return Path(state_dir) / "telegram_chat_id.json"


def save_detected_chat_id(chat_id: str) -> None:
    """Persist an auto-detected chat/channel ID for future runs."""
    import json as _json
    path = _chat_id_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({"chat_id": str(chat_id)}))


def load_detected_chat_id() -> Optional[str]:
    """Load a previously auto-detected chat/channel ID (if any)."""
    import json as _json
    path = _chat_id_store_path()
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text()).get("chat_id") or None
    except (ValueError, OSError):
        return None


def discover_channel_id(bot_token: str) -> Optional[str]:
    """
    Auto-detect the chat/channel ID from the bot's first incoming message.

    The user simply messages the bot once (or adds it as admin to a channel
    and posts). The chat ID from that update is captured — preference is
    given to a chat started by an ALLOWED user (TELEGRAM_ALLOWED_USER_IDS)
    when that list is configured.

    Handles: message, channel_post, edited_message, edited_channel_post.
    Returns the chat ID string, or None if no update is available.
    """
    import urllib.request
    import urllib.error

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=50"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    if not data.get("ok"):
        return None

    allowed = {
        uid.strip() for uid in
        os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if uid.strip()
    }

    candidates = []  # (from_allowed_user, chat_id)
    for update in data.get("result", []):
        for kind in ("message", "channel_post", "edited_message",
                     "edited_channel_post"):
            msg = update.get(kind)
            if not msg:
                continue
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            from_user = (msg.get("from") or {}).get("id")
            # Author is optional (channels have no per-message author id)
            from_allowed = str(from_user) in allowed if allowed else False
            candidates.append((from_allowed, str(chat_id)))

    if not candidates:
        return None
    # Prefer a chat involving an allowed user, else the first update seen
    candidates.sort(key=lambda t: not t[0])
    return candidates[0][1]


class TelegramClient:
    """Telegram Bot API client for pipeline communication."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: Optional[str] = None, channel_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.channel_id = channel_id or os.environ.get("TELEGRAM_CHANNEL_ID", "")

        if not self.bot_token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is required")
        # channel_id is OPTIONAL: if not set, it is auto-detected from the
        # bot's first incoming message (see _ensure_channel).

    def _ensure_channel(self) -> None:
        """Resolve the chat/channel ID, auto-detecting from the first message
        when it was not configured explicitly.

        Priority: explicit TELEGRAM_CHANNEL_ID → previously detected ID
        (persisted) → discover via getUpdates → clear error.
        """
        if self.channel_id:
            return
        detected = load_detected_chat_id()
        if detected:
            self.channel_id = detected
            logger.info("Using auto-detected Telegram chat ID: %s", detected)
            return
        discovered = discover_channel_id(self.bot_token)
        if discovered:
            self.channel_id = discovered
            save_detected_chat_id(discovered)
            logger.info(
                "Auto-detected Telegram chat ID from first message: %s "
                "(persisted; set TELEGRAM_CHANNEL_ID to override)", discovered,
            )
            return
        raise TelegramError(
            "No Telegram chat/channel ID configured. Either set "
            "TELEGRAM_CHANNEL_ID, or simply send any message to your bot "
            "once (or add it as admin to your channel and post) — the ID "
            "will be auto-detected from that first message."
        )

    def _make_request(self, method: str, data: Dict[str, Any],
                      files: Optional[Dict] = None) -> Dict:
        """Make an API request to Telegram."""
        import urllib.request
        import urllib.error
        import io

        url = self.BASE_URL.format(token=self.bot_token, method=method)

        if files:
            boundary = "----PipelineBoundary7MA4YWxkTrZu0gW"
            body = io.BytesIO()
            for key, value in data.items():
                body.write(("--" + boundary + "\r\n").encode())
                body.write(('Content-Disposition: form-data; name="' + key + '"\r\n\r\n').encode())
                body.write((str(value) + "\r\n").encode())
            for key, (filename, filedata) in files.items():
                body.write(("--" + boundary + "\r\n").encode())
                body.write(
                    ('Content-Disposition: form-data; name="' + key + '"; filename="' + filename + '"\r\n').encode()
                )
                body.write(b"Content-Type: application/octet-stream\r\n\r\n")
                body.write(filedata)
                body.write(b"\r\n")
            body.write(("--" + boundary + "--\r\n").encode())
            req = urllib.request.Request(url, data=body.getvalue())
            req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
        else:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(url, data=payload)
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                if not result.get("ok"):
                    raise TelegramError("Telegram API error: " + str(result.get("description")))
                return result.get("result", {})
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise TelegramError("HTTP " + str(e.code) + ": " + error_body)
        except urllib.error.URLError as e:
            raise TelegramError("URL error: " + str(e))

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "502", "503"])
    def send_message(self, text: str, parse_mode: str = "Markdown") -> Dict:
        """Send a text message to the configured channel."""
        self._ensure_channel()
        return self._make_request("sendMessage", {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": parse_mode,
        })

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "502"])
    def send_photo(self, photo_path: str, caption: str = "") -> Dict:
        """Send a photo to the channel."""
        self._ensure_channel()
        with open(photo_path, "rb") as f:
            filedata = f.read()
        return self._make_request("sendPhoto", {
            "chat_id": self.channel_id,
            "caption": caption,
        }, files={"photo": (Path(photo_path).name, filedata)})

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "502"])
    def send_document(self, file_path: str, caption: str = "") -> Dict:
        """Send a document/file to the channel."""
        self._ensure_channel()
        with open(file_path, "rb") as f:
            filedata = f.read()
        return self._make_request("sendDocument", {
            "chat_id": self.channel_id,
            "caption": caption,
        }, files={"document": (Path(file_path).name, filedata)})

    @retry(max_attempts=2, initial_delay=5.0, retryable_messages=["timeout", "429", "502"])
    def send_video(self, video_path: str, caption: str = "",
                   duration: Optional[int] = None, width: Optional[int] = None,
                   height: Optional[int] = None) -> Dict:
        """Send a video to the channel."""
        self._ensure_channel()
        with open(video_path, "rb") as f:
            filedata = f.read()
        data = {"chat_id": self.channel_id, "caption": caption}
        if duration:
            data["duration"] = duration
        if width:
            data["width"] = width
        if height:
            data["height"] = height
        return self._make_request("sendVideo", data,
                                  files={"video": (Path(video_path).name, filedata)})

    def send_progress(self, stage: str, status: str, detail: str = "") -> Dict:
        """Send a progress update for a pipeline stage."""
        emoji = "✅" if status == "completed" else "⏳" if status == "running" else "❌"
        text = emoji + " *" + stage + "*\nStatus: " + status
        if detail:
            text += "\n" + detail
        return self.send_message(text)

    def send_error(self, stage: str, error: str) -> Dict:
        """Send an error notification."""
        text = "❌ *Error in " + stage + "*\n```\n" + error[:500] + "\n```"
        return self.send_message(text)
