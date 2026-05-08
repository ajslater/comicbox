"""
Exponential-backoff retry decorator for online API calls.

Wraps a callable that talks to an upstream API. Retries transient errors
(rate-limit, 5xx) with exponential backoff up to `max_retries`. Honors the
upstream's `retry_after` hint when present (mokkari sets this on
`RateLimitError`). Auth errors are not retried.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")

_BASE_DELAY_S = 1.0
# Cap our own exponential-backoff schedule at 60s. Server-supplied
# retry_after hints are honored beyond this — see _MAX_RETRY_AFTER_S —
# because hitting an hourly cap (CV: 200/hr) can legitimately require
# a multi-minute wait, and hammering at 60s intervals would be rude.
_MAX_DELAY_S = 60.0
# Hard cap on honored server retry_after. 1 hour matches CV's window;
# anything longer than that and we'd rather error out so the user can
# decide whether to wait or come back later.
_MAX_RETRY_AFTER_S = 3600.0


def _is_rate_limit(exc: BaseException) -> bool:
    return type(exc).__name__ == "RateLimitError"


def _is_auth_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in {"AuthenticationError", "ApiError"} and any(
        marker in str(exc).lower() for marker in ("auth", "401", "403", "forbidden")
    )


# Exceptions that signal programmer errors / bad config — NOT retriable. The
# retry decorator should pass these through unchanged so the user sees a stack
# trace immediately rather than a noisy retry loop.
_NON_RETRIABLE: tuple[type[BaseException], ...] = (
    ImportError,  # incl. ModuleNotFoundError
    TypeError,
    AttributeError,
    NameError,
    SyntaxError,
    ValueError,  # bad URL, bad arg, etc.
)


def _is_retriable(exc: BaseException) -> bool:
    """
    Return True for transient errors worth retrying.

    Auth errors and programmer/config errors raise immediately without retry.
    """
    if _is_auth_error(exc):
        return False
    return not isinstance(exc, _NON_RETRIABLE)


def _retry_after(exc: BaseException) -> float | None:
    """Pull a `retry_after` hint from the exception, if available."""
    hint = getattr(exc, "retry_after", None)
    if hint is None:
        return None
    try:
        return float(hint)
    except (TypeError, ValueError):
        return None


def _delay_for(attempt: int) -> float:
    """Exponential schedule: 1, 2, 4, 8, 16, 32, capped at 60s."""
    return min(_BASE_DELAY_S * (2**attempt), _MAX_DELAY_S)


def with_retry(
    *,
    max_retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Wrap a callable with retry-on-rate-limit / 5xx; never retries auth errors."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not _is_retriable(exc):
                        # Programmer errors, auth errors, etc.: surface immediately.
                        raise
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    server_hint = _retry_after(exc)
                    if server_hint is not None:
                        # Server told us when to come back — honor it up to
                        # the hourly-cap-sized ceiling. Don't squeeze it
                        # down to our own short backoff schedule.
                        delay = min(server_hint, _MAX_RETRY_AFTER_S)
                    else:
                        delay = min(_delay_for(attempt), _MAX_DELAY_S)
                    cause = "rate-limit" if _is_rate_limit(exc) else type(exc).__name__
                    logger.info(
                        f"{func.__name__}: {cause}, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
