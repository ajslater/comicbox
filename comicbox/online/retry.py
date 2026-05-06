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
_MAX_DELAY_S = 60.0


def _is_rate_limit(exc: BaseException) -> bool:
    return type(exc).__name__ == "RateLimitError"


def _is_auth_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in {"AuthenticationError", "ApiError"} and any(
        marker in str(exc).lower() for marker in ("auth", "401", "403", "forbidden")
    )


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
    return min(_BASE_DELAY_S * (2 ** attempt), _MAX_DELAY_S)


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
                    if _is_auth_error(exc):
                        # Auth errors are non-retriable; surface them.
                        raise
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    delay = _retry_after(exc)
                    if delay is None:
                        delay = _delay_for(attempt)
                    delay = min(delay, _MAX_DELAY_S)
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
