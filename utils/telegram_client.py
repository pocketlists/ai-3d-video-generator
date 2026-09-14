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


class TelegramClient:
    """Telegram Bot API client for pipeline communication."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: Optional[str] = None, channel_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.channel_id = channel_id or os.environ.get("TELEGRAM_CHANNEL_ID", "")

        if not self.bot_token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is required")
        if not self.channel_id:
            raise TelegramError("TELEGRAM_CHANNEL_ID is required")

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
        return self._make_request("sendMessage", {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": parse_mode,
        })

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "502"])
    def send_photo(self, photo_path: str, caption: str = "") -> Dict:
        """Send a photo to the channel."""
        with open(photo_path, "rb") as f:
            filedata = f.read()
        return self._make_request("sendPhoto", {
            "chat_id": self.channel_id,
            "caption": caption,
        }, files={"photo": (Path(photo_path).name, filedata)})

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "502"])
    def send_document(self, file_path: str, caption: str = "") -> Dict:
        """Send a document/file to the channel."""
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
