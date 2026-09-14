"""
Retry decorator — exponential backoff retry for recoverable failures.

Used throughout the pipeline to handle transient failures (network errors,
Blender crashes, Telegram API rate limits, etc.).
"""
import functools
import logging
import time
from typing import Callable, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    retryable_messages: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator that retries a function on failure with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including the first).
        initial_delay: Delay before first retry in seconds.
        backoff_factor: Multiplier for delay after each attempt.
        max_delay: Maximum delay between retries.
        retryable_exceptions: Tuple of exception types to retry on.
            Defaults to all exceptions.
        retryable_messages: List of substrings; if any appears in the
            exception message, the call is retried.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"{func.__name__} succeeded on attempt {attempt}")
                    return result
                except Exception as e:
                    last_exception = e

                    # Check if exception is retryable
                    if retryable_exceptions and not isinstance(e, retryable_exceptions):
                        raise

                    if retryable_messages:
                        msg = str(e).lower()
                        if not any(s.lower() in msg for s in retryable_messages):
                            raise

                    if attempt < max_attempts:
                        actual_delay = min(delay, max_delay)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {actual_delay:.1f}s..."
                        )
                        time.sleep(actual_delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


def is_retryable_error(error: Exception, known_errors: List[str]) -> bool:
    """Check if an error matches any known retryable error patterns."""
    msg = str(error).lower()
    return any(pattern.lower() in msg for pattern in known_errors)
