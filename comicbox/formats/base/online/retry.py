"""
Exponential-backoff retry decorator for online API calls.

Wraps a callable that talks to an upstream API. Retries transient errors
(rate-limit, 5xx) with exponential backoff up to `max_retries`. Honors the
upstream's `retry_after` hint when present (mokkari sets this on
`RateLimitError`). Permanent failures — auth errors and not-found
responses — are never retried.
"""

from __future__ import annotations

import re
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Final, TypeVar

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")

# ComicVine sends the API key as a query param (simyan 3.x), and requests
# embeds the full URL — key included — in HTTPError/ConnectionError
# messages that ride along as ``__cause__`` of every simyan error.
_API_KEY_RE: Final = re.compile(r"(api_key=)[^&\s'\"]+")


def _scrub_node_and_link(node: BaseException) -> list[BaseException]:
    """Redact one exception's string args in place; return linked nodes."""
    node.args = tuple(
        _API_KEY_RE.sub(r"\1REDACTED", arg) if isinstance(arg, str) else arg
        for arg in node.args
    )
    links = [arg for arg in node.args if isinstance(arg, BaseException)]
    if node.__cause__ is not None:
        links.append(node.__cause__)
    if node.__context__ is not None and not node.__suppress_context__:
        links.append(node.__context__)
    return links


def _redact_api_keys(exc: BaseException) -> None:
    """
    Scrub ``api_key=`` query values from an exception chain, in place.

    Message-only logging (``f"{exc}"``) never prints the chain, but a
    full traceback (``logger.exception``, or an embedding application's
    error handler) renders every ``__cause__``/``__context__`` message.
    Scrubbing here — every online API call passes through the retry
    wrapper — protects all downstream consumers. Nested exception
    objects inside ``args`` (e.g. urllib3's ``MaxRetryError`` carried by
    requests' ``ConnectionError``) are scrubbed too.
    """
    stack: list[BaseException] = [exc]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        stack.extend(_scrub_node_and_link(node))


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

# Rate-limit-specific backoff schedule. Different from the generic
# exponential because rate-limit recovery is fundamentally about waiting
# for a sliding window to clear, not about retrying a transient failure.
#
# ComicVine's 200/hr cap means once tripped, you may need to wait
# minutes for the rolling window to slide forward. Our generic 1-2-4-8-16
# schedule tops out at 31s total — far too short for an hourly cap.
# This schedule starts at 30s (one second-bucket reset plus margin) and
# escalates to 10-min waits, then plateaus there for the tail. Enough
# to clear a typical hourly-cap hit without giving up on transient
# server-side enforcement glitches (clock skew, burst protection) that
# locally-paced 1/sec calls occasionally trip.
#
# The plateau-tail matters under -j N parallel batches: the
# 2026-05-15-stress-100 run quantified retry-exhaustion cascades on
# high-fan-out fixtures (a single Conan-titled fixture fans out to 20+
# candidate series, all hitting Metron's 20/min cap simultaneously
# under -j 8). 5 attempts wasn't enough to clear the cascade for some
# candidates — 8 attempts gives a worker that gets repeatedly bucketed
# enough room to recover without dropping its series.
#
# Honored only when there's no server-supplied `retry_after` hint;
# mokkari sets that explicitly, simyan does not.
_RATE_LIMIT_SCHEDULE: Final[tuple[float, ...]] = (
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    600.0,
    600.0,
    600.0,
)

# Max retry attempts for rate-limit errors specifically. Generic errors
# stay at `max_retries=5` (31s total budget for transient 5xx). Going
# higher for rate-limit gives the schedule above room to play out fully.
_MAX_RATE_LIMIT_RETRIES: Final[int] = len(_RATE_LIMIT_SCHEDULE)


def _is_rate_limit(exc: BaseException) -> bool:
    if type(exc).__name__ == "RateLimitError":
        return True
    # simyan 3.x client-side cap exhaustion surfaces as ServiceError whose
    # __cause__ is requests' Timeout("Rate limit not cleared within
    # max_delay=..."). Route it to the rate-limit schedule — the generic
    # 31s budget can't outlast an hourly cap.
    return (
        type(exc).__name__ == "ServiceError"
        and "rate limit not cleared" in str(exc.__cause__ or "").lower()
    )


_AUTH_MARKERS = (
    "auth",
    "401",
    "403",
    "forbidden",
    # mokkari raises its generic ApiError with the server's message for
    # bad Metron credentials; simyan's AuthenticationError carries CV's
    # marker-less "Invalid API Key".
    "invalid username",
    "invalid password",
    "api key",
)


def _is_auth_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name == "AuthenticationError":
        # The class name alone is conclusive; the message is whatever the
        # server sent (CV: "Invalid API Key", no recognizable marker).
        return True
    return name == "ApiError" and any(
        marker in str(exc).lower() for marker in _AUTH_MARKERS
    )


def _is_not_found_error(exc: BaseException) -> bool:
    """Permanent not-found responses (bad explicit id) — never retriable."""
    if type(exc).__name__ != "ServiceError":
        return False
    if getattr(exc.__cause__, "status_code", None) == 404:  # noqa: PLR2004
        return True
    return "not found" in str(exc).lower()


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
    LookupError,  # "issue N not found" from sources; incl. KeyError/IndexError
)


def _is_retriable(exc: BaseException) -> bool:
    """
    Return True for transient errors worth retrying.

    Auth errors, not-found responses, and programmer/config errors raise
    immediately without retry.
    """
    if _is_auth_error(exc) or _is_not_found_error(exc):
        return False
    return not isinstance(exc, _NON_RETRIABLE)


def _retry_after(exc: BaseException) -> float | None:
    """
    Pull a `retry_after` hint from the exception, if available.

    A non-positive hint is treated as no hint: mokkari's server-side 429
    path sets `retry_after` to 0.0 when Metron omits the `Retry-After`
    header, and honoring that literally would mean up to a full budget of
    zero-delay retries instead of the rate-limit schedule.
    """
    hint = getattr(exc, "retry_after", None)
    if hint is None:
        return None
    try:
        value = float(hint)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _delay_for(attempt: int) -> float:
    """Exponential schedule: 1, 2, 4, 8, 16, 32, capped at 60s."""
    return min(_BASE_DELAY_S * (2**attempt), _MAX_DELAY_S)


def _delay_for_rate_limit(attempt: int) -> float:
    """Longer schedule for rate-limit hits with no server hint."""
    if attempt >= len(_RATE_LIMIT_SCHEDULE):
        return _RATE_LIMIT_SCHEDULE[-1]
    return _RATE_LIMIT_SCHEDULE[attempt]


def _plan_retry(
    exc: BaseException,
    *,
    attempt: int,
    rate_limit_attempt: int,
    max_retries: int,
) -> tuple[float, str, bool] | None:
    """
    Decide whether and how to retry. Returns (delay, budget_label, is_rate_limit).

    Returns ``None`` when the applicable budget is exhausted. Rate-limit
    errors have their own budget (`_MAX_RATE_LIMIT_RETRIES`) and schedule
    (`_RATE_LIMIT_SCHEDULE`); generic retriable errors use the caller's
    `max_retries` and the exponential schedule. A server-supplied
    `retry_after` hint always wins over both.
    """
    is_rate_limit = _is_rate_limit(exc)
    if is_rate_limit:
        if rate_limit_attempt >= _MAX_RATE_LIMIT_RETRIES:
            return None
    elif attempt >= max_retries:
        return None
    server_hint = _retry_after(exc)
    if server_hint is not None:
        delay = min(server_hint, _MAX_RETRY_AFTER_S)
    elif is_rate_limit:
        delay = _delay_for_rate_limit(rate_limit_attempt)
    else:
        delay = min(_delay_for(attempt), _MAX_DELAY_S)
    if is_rate_limit:
        budget = (
            f"rate-limit attempt {rate_limit_attempt + 1}/{_MAX_RATE_LIMIT_RETRIES}"
        )
    else:
        budget = f"attempt {attempt + 1}/{max_retries}"
    return delay, budget, is_rate_limit


def _handle_retry_exception(
    exc: Exception,
    *,
    func_name: str,
    attempt: int,
    rate_limit_attempt: int,
    max_retries: int,
    sleep: Callable[[float], None],
) -> bool:
    """
    Sleep through one retriable failure. Return True iff the budget remains.

    Raises ``exc`` immediately when it's non-retriable (programmer / auth
    errors); returns False when the applicable budget is exhausted so the
    caller can break out of its retry loop.
    """
    if not _is_retriable(exc):
        raise exc
    plan = _plan_retry(
        exc,
        attempt=attempt,
        rate_limit_attempt=rate_limit_attempt,
        max_retries=max_retries,
    )
    if plan is None:
        return False
    delay, budget, is_rate_limit = plan
    cause = "rate-limit" if is_rate_limit else type(exc).__name__
    logger.info(f"{func_name}: {cause}, retrying in {delay:.1f}s ({budget})")
    sleep(delay)
    return True


def _notify_rate_limit_listener(
    exc: BaseException,
    args: tuple[Any, ...],
    *,
    attempt: int,
    rate_limit_attempt: int,
    max_retries: int,
) -> None:
    """Invoke ``instance.on_rate_limit`` for rate-limit failures, if defined."""
    if not args or not _is_rate_limit(exc):
        return
    instance_cb = getattr(args[0], "on_rate_limit", None)
    if instance_cb is None:
        return
    plan = _plan_retry(
        exc,
        attempt=attempt,
        rate_limit_attempt=rate_limit_attempt,
        max_retries=max_retries,
    )
    delay = plan[0] if plan else None
    source_name = getattr(args[0], "name", "")
    instance_cb(source_name, delay)


def _resolve_sleep(
    args: tuple[Any, ...], default_sleep: Callable[[float], None]
) -> Callable[[float], None]:
    """
    Prefer a ``retry_sleep`` supplied by the instance at call time.

    The decorator's ``sleep`` argument binds at class-definition time, so a
    per-session cancellable sleep (OnlineSession wires waits to its cancel
    event) can only be injected through the instance — the same pattern as
    the ``on_rate_limit`` listener above. The instance sleep may raise to
    abort the retry loop; the exception propagates to the caller unchanged.
    """
    if args:
        instance_sleep = getattr(args[0], "retry_sleep", None)
        if instance_sleep is not None:
            return instance_sleep
    return default_sleep


def _run_with_retries(
    func: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    max_retries: int,
    sleep: Callable[[float], None],
) -> T:
    """Drive ``func`` through the retry budget; re-raise on exhaustion."""
    sleep = _resolve_sleep(args, sleep)
    last_exc: BaseException | None = None
    attempt = 0
    rate_limit_attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            _redact_api_keys(exc)
            last_exc = exc
            _notify_rate_limit_listener(
                exc,
                args,
                attempt=attempt,
                rate_limit_attempt=rate_limit_attempt,
                max_retries=max_retries,
            )
            if not _handle_retry_exception(
                exc,
                func_name=func.__name__,  # ty: ignore[unresolved-attribute]
                attempt=attempt,
                rate_limit_attempt=rate_limit_attempt,
                max_retries=max_retries,
                sleep=sleep,
            ):
                break
            if _is_rate_limit(exc):
                rate_limit_attempt += 1
            else:
                attempt += 1
    assert last_exc is not None
    raise last_exc


def with_retry(
    *,
    max_retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Wrap a callable with retry-on-rate-limit / 5xx; never retries auth errors.

    Rate-limit errors get a separate retry budget (`_MAX_RATE_LIMIT_RETRIES`)
    and a longer delay schedule (`_RATE_LIMIT_SCHEDULE`) than other
    retriable failures. The generic 1-2-4-8-16s schedule tops out at 31s
    of total wait, which is far too short for hourly-cap recovery
    (ComicVine's 200/hr can require several minutes to clear). The
    rate-limit schedule (30s, 1m, 2m, 5m, 10m) gives that window time to
    slide forward.

    When the exception carries a `retry_after` attribute (mokkari does
    this), we honor it directly — server hint always wins over our
    blind schedules.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return _run_with_retries(
                func, args, kwargs, max_retries=max_retries, sleep=sleep
            )

        return wrapper

    return decorator
