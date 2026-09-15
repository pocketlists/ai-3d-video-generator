"""
Error classifier — classifies errors for retry/escalation decisions.

Classifications:
- TRANSIENT: Network timeout, temporary failure → retry
- RATE_LIMIT: 429, quota exceeded → retry with backoff
- AUTH: 401, 403, invalid key → no retry, escalate
- INVALID_INPUT: 400, malformed request → no retry, escalate
- PROVIDER_ERROR: 500, 502, 503 → retry with backoff
- OUT_OF_MEMORY: OOM, killed → reduce workload, retry
- BLENDER_ERROR: Blender crash → retry once, escalate
- FFMPEG_ERROR: FFmpeg failure → retry, escalate
- QUALITY_FAILURE: QC failed → retry, escalate
- HUMAN_INTERVENTION: Requires human input → escalate, wait
"""
import re
from typing import Optional


class ErrorType:
    TRANSIENT = "TRANSIENT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH = "AUTH"
    INVALID_INPUT = "INVALID_INPUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    BLENDER_ERROR = "BLENDER_ERROR"
    FFMPEG_ERROR = "FFMPEG_ERROR"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"
    UNKNOWN = "UNKNOWN"


# Patterns for classification
PATTERNS = [
    (ErrorType.RATE_LIMIT, [r"429", r"rate.?limit", r"quota", r"too many requests", r"RESOURCE_EXHAUSTED"]),
    (ErrorType.AUTH, [r"401", r"403", r"unauthorized", r"forbidden", r"invalid.*key", r"authentication"]),
    (ErrorType.INVALID_INPUT, [r"400", r"bad.?request", r"invalid.?input", r"malformed", r"validation"]),
    (ErrorType.OUT_OF_MEMORY, [r"out.?of.?memory", r"oom", r"killed", r"memory.?error", r"ENOMEM"]),
    (ErrorType.BLENDER_ERROR, [r"blender", r"eevee", r"cycles", r"gl.?error", r"EGL", r"OpenGL"]),
    (ErrorType.FFMPEG_ERROR, [r"ffmpeg", r"ffprobe", r"codec", r"encoder", r"decoder"]),
    (ErrorType.QUALITY_FAILURE, [r"quality.?check.?fail", r"corrupt", r"missing.?frame", r"black.?frame"]),
    (ErrorType.TRANSIENT, [r"timeout", r"timed.?out", r"connection.?reset", r"connection.?refused",
                           r"temporarily", r"502", r"503", r"504", r"network"]),
]


def classify_error(error: str) -> str:
    """Classify an error string. Returns ErrorType."""
    error_lower = str(error).lower()
    for error_type, patterns in PATTERNS:
        for pattern in patterns:
            if re.search(pattern, error_lower):
                return error_type
    return ErrorType.UNKNOWN


def should_retry(error_type: str, attempt: int, max_attempts: int = 3) -> bool:
    """Determine if an error should be retried."""
    if attempt >= max_attempts:
        return False
    retryable = {
        ErrorType.TRANSIENT, ErrorType.RATE_LIMIT, ErrorType.PROVIDER_ERROR,
        ErrorType.OUT_OF_MEMORY, ErrorType.BLENDER_ERROR, ErrorType.FFMPEG_ERROR,
    }
    return error_type in retryable


def should_escalate(error_type: str, attempts_exhausted: bool = False) -> bool:
    """Determine if an error should be escalated to Telegram."""
    escalate_types = {
        ErrorType.AUTH, ErrorType.INVALID_INPUT, ErrorType.HUMAN_INTERVENTION,
        ErrorType.QUALITY_FAILURE,
    }
    return error_type in escalate_types or attempts_exhausted


def get_retry_delay(error_type: str, attempt: int) -> float:
    """Get retry delay in seconds based on error type and attempt."""
    base_delay = {
        ErrorType.RATE_LIMIT: 10.0,
        ErrorType.TRANSIENT: 3.0,
        ErrorType.PROVIDER_ERROR: 5.0,
        ErrorType.OUT_OF_MEMORY: 10.0,
        ErrorType.BLENDER_ERROR: 5.0,
        ErrorType.FFMPEG_ERROR: 3.0,
    }.get(error_type, 3.0)
    return base_delay * (2 ** (attempt - 1))
