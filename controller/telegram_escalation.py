"""
Telegram escalation — no 5-minute timeout, runner exits, resume via new workflow.

When a critical provider fails:
1. Retry automatically (with error classification)
2. If still failed: save checkpoint
3. Send Telegram escalation with JOB_ID, STAGE, ERROR, PROVIDER, RESUME_TOKEN
4. Set state to WAITING_FOR_EXTERNAL_RESPONSE
5. EXIT the current workflow runner cleanly (no wasting minutes waiting)

A future Telegram response starts a NEW workflow (resume.yml) which:
- Validates job_id and resume_token
- Loads persistent checkpoint
- Stores external response
- Resumes the exact failed stage

NO automatic fallback after timeout for human intervention.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from utils.logger import PipelineLogger
from utils.error_classifier import classify_error, should_retry, should_escalate


class EscalationError(Exception):
    pass


class TelegramEscalation:
    """Telegram-based failure escalation with resume tokens."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("escalation")
        self.bot_token = config.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.channel_id = config.get("telegram_channel_id") or os.environ.get("TELEGRAM_CHANNEL_ID", "")
        self.enabled = bool(self.bot_token and self.channel_id)
        self.allowed_user_ids = self._parse_allowed_users()

    def _parse_allowed_users(self) -> list:
        raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        if not raw:
            return []
        return [uid.strip() for uid in raw.split(",") if uid.strip()]

    def escalate_failure(self, job_id: str, stage: str, error: str, provider: str = "",
                         context: str = "") -> Dict[str, Any]:
        """
        Escalate failure to Telegram and EXIT — no waiting.

        Returns escalation info dict (does NOT wait for response).
        The runner should exit after this call.
        """
        # Resume token is ALWAYS generated — it is the resume key for resume.yml,
        # independent of whether the Telegram delivery itself succeeded.
        resume_token = f"resume_{job_id}_{stage}_{uuid.uuid4().hex[:8]}"

        if not self.enabled:
            self.logger.warning(
                "Telegram not configured, cannot escalate — "
                "returning escalation info (resume token still valid for resume.yml)"
            )
            return {"escalated": False, "resume_token": resume_token,
                    "reason": "telegram_not_configured"}

        message_id = self._send_escalation_message(job_id, stage, error, provider, context, resume_token)

        return {
            "escalated": True,
            "resume_token": resume_token,
            "message_id": message_id,
            "instructions": (
                f"To resume this job, run the 'Resume Pipeline' workflow with:\n"
                f"- job_id: {job_id}\n"
                f"- stage: {stage}\n"
                f"- resume_token: {resume_token}"
            ),
        }

    def _send_escalation_message(self, job_id: str, stage: str, error: str,
                                  provider: str, context: str, resume_token: str) -> Optional[int]:
        """Send escalation message with structured format."""
        text = (
            f"AI STAGE FAILED\n\n"
            f"JOB_ID: {job_id}\n"
            f"STAGE: {stage}\n"
            f"PROVIDER: {provider or 'unknown'}\n"
            f"ERROR: {error[:300]}\n\n"
            f"EXPECTED_RESPONSE: corrected plan JSON or alternative instruction\n\n"
            f"RESUME_TOKEN: {resume_token}\n\n"
            f"To resume: Reply to this message or run the Resume Pipeline workflow\n"
            f"with job_id={job_id}, stage={stage}, resume_token={resume_token}\n\n"
            f"STATUS: WAITING_FOR_EXTERNAL_RESPONSE"
        )

        result = self._send_message(text)
        if result:
            msg_id = result.get("message_id")
            self.logger.info(f"Escalation sent: message_id={msg_id}, token={resume_token}")
            return msg_id
        return None

    def parse_telegram_response(self, update: Dict) -> Optional[Dict]:
        """
        Parse a Telegram update to extract a resume response.

        Supports: normal message, reply to escalation, channel post, bot command.
        Validates authorization if TELEGRAM_ALLOWED_USER_IDS is configured.
        """
        message = None
        if "message" in update:
            message = update["message"]
        elif "channel_post" in update:
            message = update["channel_post"]
        elif "edited_message" in update:
            message = update["edited_message"]
        elif "edited_channel_post" in update:
            message = update["edited_channel_post"]

        if not message:
            return None

        text = message.get("text", "")
        if not text:
            return None

        # Check authorization
        if self.allowed_user_ids:
            user = message.get("from", {})
            user_id = str(user.get("id", ""))
            if user_id not in self.allowed_user_ids:
                self.logger.warning(f"Unauthorized Telegram user: {user_id}")
                return None

        # Check for reply_to_message (escalation reply)
        reply_to = message.get("reply_to_message", {})
        reply_text = reply_to.get("text", "")

        # Extract job_id and resume_token from the response
        job_id = self._extract_field(text, "JOB_ID") or self._extract_field(reply_text, "JOB_ID")
        resume_token = self._extract_field(text, "RESUME_TOKEN") or self._extract_field(reply_text, "RESUME_TOKEN")
        stage = self._extract_field(text, "STAGE") or self._extract_field(reply_text, "STAGE")

        # Try to parse response content as JSON
        response_content = self._extract_response_content(text)

        if job_id or resume_token:
            return {
                "job_id": job_id,
                "stage": stage,
                "resume_token": resume_token,
                "response": response_content or text,
                "message_id": message.get("message_id"),
                "reply_to_message_id": reply_to.get("message_id"),
                "chat_id": message.get("chat", {}).get("id"),
                "user_id": message.get("from", {}).get("id"),
            }

        return None

    def _extract_field(self, text: str, field: str) -> Optional[str]:
        """Extract 'FIELD: value' from text."""
        import re
        pattern = rf"{field}\s*[:=]\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_response_content(self, text: str) -> Optional[str]:
        """Extract JSON response from text if present."""
        import re
        # Look for JSON blocks
        matches = re.findall(r'\{[^{}]*\}', text, re.DOTALL)
        if matches:
            return max(matches, key=len)
        return None

    def validate_resume_token(self, job_id: str, stage: str, resume_token: str,
                               stored_token: str) -> bool:
        """Validate a resume token matches the stored one."""
        if not stored_token:
            return False
        return resume_token == stored_token

    def _send_message(self, text: str) -> Optional[Dict]:
        """Send a text message to Telegram."""
        if not self.enabled:
            return None
        import urllib.request
        import urllib.error

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({"chat_id": self.channel_id, "text": text}).encode()
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

    def send_progress(self, job_id: Optional[str], stage: str, status: str) -> None:
        if not self.enabled:
            return
        text = f"[{status}] {stage}"
        if job_id:
            text = f"Job {job_id} — {text}"
        self._send_message(text)

    def send_error(self, job_id: Optional[str], stage: str, error: str,
                   permanent: bool = False) -> None:
        if not self.enabled:
            return
        label = "[PERMANENT ERROR]" if permanent else "[ERROR]"
        text = f"{label} Job {job_id} — Stage {stage}\n{error[:300]}"
        self._send_message(text)

    def send_final_report(self, job_id: str, status: str, duration: float,
                          resolution: str, fps: int, render_time: float,
                          worker_count: int, avg_frame_time: float,
                          quality_score: float, warnings: list) -> None:
        """Send final delivery report with all metrics."""
        if not self.enabled:
            return
        text = (
            f"FINAL VIDEO DELIVERED\n\n"
            f"JOB_ID: {job_id}\n"
            f"STATUS: {status}\n"
            f"DURATION: {duration:.1f}s\n"
            f"RESOLUTION: {resolution}\n"
            f"FPS: {fps}\n"
            f"TOTAL_RENDER_TIME: {render_time:.1f}s\n"
            f"ACTUAL_WORKERS: {worker_count}\n"
            f"AVG_FRAME_TIME: {avg_frame_time:.2f}s\n"
            f"QUALITY_SCORE: {quality_score:.1f}\n"
            f"WARNINGS: {', '.join(warnings) if warnings else 'none'}"
        )
        self._send_message(text)
