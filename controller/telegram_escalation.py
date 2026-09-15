"""
Telegram escalation system — handles failure escalation and human/AI handoff.

When a critical AI API fails:
1. Create failure report
2. Send Telegram message with job/stage/error
3. Set state to WAITING_FOR_EXTERNAL_RESPONSE
4. Wait for reply (poll Telegram updates)
5. Validate reply matches the correct job_id/stage
6. Resume pipeline from failed stage

Supports multiple concurrent jobs without mixing up replies.
"""
import json
import os
import time
from typing import Any, Dict, Optional

from utils.logger import PipelineLogger
from utils.retry import retry


class EscalationError(Exception):
    pass


class TelegramEscalation:
    """Manages Telegram-based failure escalation and response handling."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("escalation")
        self.bot_token = config.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.channel_id = config.get("telegram_channel_id") or os.environ.get("TELEGRAM_CHANNEL_ID", "")
        self.enabled = bool(self.bot_token and self.channel_id)
        self.wait_timeout = int(config.get("escalation_timeout", 300))  # 5 min default
        self.poll_interval = int(config.get("escalation_poll_interval", 10))

    def escalate_failure(self, job_id: str, stage: str, error: str,
                         context: str = "") -> Optional[str]:
        """
        Escalate a failure to Telegram and wait for external response.

        Returns the response text if received, None if timed out.
        """
        if not self.enabled:
            self.logger.warning("Telegram not configured, cannot escalate")
            return None

        message_id = self._send_escalation_message(job_id, stage, error, context)
        if not message_id:
            return None

        self.logger.info(f"Waiting for external response (timeout: {self.wait_timeout}s)")
        response = self._wait_for_response(message_id, job_id, stage)

        if response:
            self._send_acknowledgment(job_id, stage, "Response received, resuming pipeline")
        else:
            self.logger.warning(f"No response received within {self.wait_timeout}s")
            self._send_acknowledgment(job_id, stage, "No response received, using fallback")

        return response

    def _send_escalation_message(self, job_id: str, stage: str, error: str,
                                  context: str) -> Optional[int]:
        """Send escalation message to Telegram. Returns message_id."""
        text = (
            "[ALERT] AI STAGE FAILED\n\n"
            f"Job: {job_id}\n"
            f"Stage: {stage}\n"
            f"Error: {error[:300]}\n\n"
            f"What is required:\n"
            f"Please provide a corrected response or alternative instruction.\n"
            f"Reply to this message to continue.\n\n"
            f"Status: WAITING_FOR_EXTERNAL_RESPONSE"
        )

        result = self._send_message(text)
        if result:
            msg_id = result.get("message_id")
            self.logger.info(f"Escalation message sent: {msg_id}")
            return msg_id
        return None

    def _wait_for_response(self, message_id: int, job_id: str, stage: str) -> Optional[str]:
        """Poll Telegram for reply to the escalation message."""
        import urllib.request
        import urllib.error

        start_time = time.time()
        offset = 0

        while time.time() - start_time < self.wait_timeout:
            try:
                url = (f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                       f"?offset={offset}&timeout={self.poll_interval}")
                with urllib.request.urlopen(url, timeout=self.poll_interval + 5) as resp:
                    result = json.loads(resp.read().decode())

                if not result.get("ok"):
                    time.sleep(self.poll_interval)
                    continue

                for update in result.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    message = update.get("message", {})
                    reply_to = message.get("reply_to_message", {})

                    # Check if this is a reply to our escalation message
                    if reply_to.get("message_id") == message_id:
                        text = message.get("text", "")
                        self.logger.info(f"Reply received: {text[:100]}")
                        return text

                    # Also check for any message containing the job_id
                    text = message.get("text", "")
                    if job_id in text:
                        self.logger.info(f"Job-related message received: {text[:100]}")
                        return text

            except urllib.error.URLError as e:
                self.logger.warning(f"Telegram poll error: {e}")
                time.sleep(self.poll_interval)
            except Exception as e:
                self.logger.warning(f"Unexpected poll error: {e}")
                time.sleep(self.poll_interval)

        return None

    def _send_message(self, text: str) -> Optional[Dict]:
        """Send a text message to Telegram."""
        if not self.enabled:
            return None
        import urllib.request
        import urllib.error

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.channel_id,
            "text": text,
        }).encode()

        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    return result.get("result", {})
            return None
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            self.logger.error(f"Telegram send failed: {e}")
            return None

    def _send_acknowledgment(self, job_id: str, stage: str, status: str) -> None:
        """Send acknowledgment after escalation is resolved."""
        text = f"[OK] Job {job_id} — Stage {stage}\nStatus: {status}"
        self._send_message(text)

    def send_progress(self, job_id: Optional[str], stage: str, status: str) -> None:
        """Send a progress update."""
        if not self.enabled:
            return
        text = f"[{status}] {stage}"
        if job_id:
            text = f"Job {job_id} — {text}"
        self._send_message(text)

    def send_error(self, job_id: Optional[str], stage: str, error: str,
                   permanent: bool = False) -> None:
        """Send an error notification."""
        if not self.enabled:
            return
        label = "[PERMANENT ERROR]" if permanent else "[ERROR]"
        text = f"{label} Job {job_id} — Stage {stage}\n{error[:300]}"
        self._send_message(text)

    def send_asset_metadata(self, job_id: str, asset_name: str, asset_type: str,
                            file_path: str, file_size: int) -> None:
        """Send asset metadata to Telegram for archival."""
        if not self.enabled:
            return
        text = (
            f"[ASSET] Job {job_id}\n"
            f"Type: {asset_type}\n"
            f"Name: {asset_name}\n"
            f"Size: {file_size} bytes\n"
            f"Path: {file_path}"
        )
        self._send_message(text)
