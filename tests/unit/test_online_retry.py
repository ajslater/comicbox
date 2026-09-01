"""Retry decorator tests."""

from __future__ import annotations

from functools import partial, wraps
from typing import TYPE_CHECKING, Any, TypeVar

import pytest

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.retry import (
    _MAX_TOTAL_WAIT_S,
    _RATE_LIMIT_SCHEDULE,
    RetryCategory,
    clear_cancel,
    interruptible_sleep,
    request_cancel,
    with_retry,
)

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class _RateLimitedError(Exception):
    """Stands in for a client library's rate-limit error."""

    def __init__(
        self, msg: str = "rate limited", retry_after: float | None = None
    ) -> None:
        super().__init__(msg)
        if retry_after is not None:
            self.retry_after = retry_after


class _AuthFailedError(Exception):
    """Stands in for a client library's auth error."""


class _NotFoundError(Exception):
    """Stands in for a client library's permanent not-found response."""


class _StubSource:
    """The minimal source shape the retry decorator reads off ``args[0]``."""

    name = "stub"
    on_rate_limit: Any = None
    retry_sleep: Any = None

    @staticmethod
    def classify_retry_exception(exc: BaseException) -> RetryCategory | None:
        if isinstance(exc, _RateLimitedError):
            return RetryCategory.RATE_LIMIT
        if isinstance(exc, _AuthFailedError):
            return RetryCategory.AUTH
        if isinstance(exc, _NotFoundError):
            return RetryCategory.NOT_FOUND
        return None


def _stub_retry(
    source: _StubSource | None = None, **retry_kwargs: Any
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Like ``with_retry``, but bound to a stub source instance as ``args[0]``."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @with_retry(**retry_kwargs)
        @wraps(func)
        def method(_self: _StubSource, *args: Any, **kwargs: Any) -> T:
            return func(*args, **kwargs)

        return partial(method, source if source is not None else _StubSource())

    return decorator


def _capture_sleeps() -> tuple[list[float], Callable[[float], None]]:
    sleeps: list[float] = []

    def _sleep(s: float) -> None:
        sleeps.append(s)

    return sleeps, _sleep


def test_returns_immediately_on_success() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert fn() == "ok"
    assert calls == 1
    assert sleeps == []


def test_generic_retriable_retries_with_exponential_schedule() -> None:
    """Non-rate-limit retriable errors use the 1-2-4-8-16s schedule."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            msg = "transient"
            raise RuntimeError(msg)
        return "ok"

    assert fn() == "ok"
    assert calls == 3
    # Generic schedule: 1s, 2s.
    assert sleeps == [1.0, 2.0]


def test_rate_limit_retries_use_longer_schedule() -> None:
    """
    Rate-limit errors get a much longer per-attempt delay than generic errors.

    Generic schedule tops out at 31s of total wait (1+2+4+8+16) — far too
    short for ComicVine's 200/hr cap to recover. The rate-limit schedule
    starts at 30s and escalates into the minutes.
    """
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _RateLimitedError
        return "ok"

    assert fn() == "ok"
    assert calls == 3
    # Two sleeps before the third successful call — first two slots of
    # the rate-limit schedule.
    assert sleeps == [_RATE_LIMIT_SCHEDULE[0], _RATE_LIMIT_SCHEDULE[1]]


def test_honors_retry_after_hint_over_rate_limit_schedule() -> None:
    """Server-supplied retry_after always wins, even for rate-limit errors."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _RateLimitedError(retry_after=12.5)
        return "ok"

    fn()
    # Hint wins over our 30s default first slot.
    assert sleeps == [12.5]


def test_zero_retry_after_hint_falls_back_to_schedule() -> None:
    """
    Treat a non-positive hint as no hint.

    mokkari sets retry_after=0.0 on a 429 when Metron omits the
    Retry-After header, and honoring that literally would mean
    zero-delay hammering instead of backoff.
    """
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _RateLimitedError(retry_after=0.0)
        return "ok"

    fn()
    assert sleeps == [_RATE_LIMIT_SCHEDULE[0]]


def test_max_retries_exhausted_for_generic_error() -> None:
    """`max_retries` governs the generic-error budget."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(max_retries=2, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        msg = "transient"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="transient"):
        fn()
    # max_retries=2 means 1 + 2 retry attempts = 3 calls, with 2 sleeps.
    assert calls == 3
    assert sleeps == [1.0, 2.0]


def test_rate_limit_has_its_own_budget() -> None:
    """
    Rate-limit errors get `_MAX_RATE_LIMIT_RETRIES` retries (not `max_retries`).

    `max_retries=1` would only get 1 retry for a generic error, but
    rate-limit errors get the full rate-limit schedule (~5 retries) so
    a transient 5xx storm can't exhaust the hourly-cap recovery budget.
    """
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(max_retries=1, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _RateLimitedError

    with pytest.raises(_RateLimitedError):
        fn()
    # 1 + len(_RATE_LIMIT_SCHEDULE) attempts, with len(schedule) sleeps.
    assert calls == 1 + len(_RATE_LIMIT_SCHEDULE)
    assert sleeps == list(_RATE_LIMIT_SCHEDULE)


def test_auth_error_does_not_retry() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0
    msg = "401 unauthorized"

    @_stub_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _AuthFailedError(msg)

    with pytest.raises(_AuthFailedError):
        fn()
    assert calls == 1
    assert sleeps == []


def test_base_source_declines_every_exception() -> None:
    """
    A source that doesn't override the hook classifies nothing.

    The decorator then applies its conservative fallback, so a new source
    degrades to generic retries rather than inheriting another library's
    taxonomy.
    """
    from comicbox.formats.base.online.sources.base import OnlineSource

    assert OnlineSource.classify_retry_exception(RuntimeError("boom")) is None


def test_rate_limit_notifies_the_instance_listener() -> None:
    """
    A RATE_LIMIT verdict fires `on_rate_limit`, which drives the user notice.

    `online_lookup` wires this to the `RateLimited` event, so a source
    whose classifier stopped saying RATE_LIMIT would still retry — just
    silently, leaving the user staring at an unexplained stall.
    """
    _sleeps, fake_sleep = _capture_sleeps()
    notices: list[tuple[str, float | None]] = []

    class _ListeningSource(_StubSource):
        on_rate_limit: Any = staticmethod(
            lambda name, delay: notices.append((name, delay))
        )

    calls = 0

    @_stub_retry(_ListeningSource(), max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _RateLimitedError
        return "ok"

    assert fn() == "ok"
    assert notices == [("stub", _RATE_LIMIT_SCHEDULE[0])]


def test_transient_error_does_not_notify_the_listener() -> None:
    """Only rate limits reach `on_rate_limit`; a generic 5xx must not."""
    _sleeps, fake_sleep = _capture_sleeps()
    notices: list[tuple[str, float | None]] = []

    class _ListeningSource(_StubSource):
        on_rate_limit: Any = staticmethod(
            lambda name, delay: notices.append((name, delay))
        )

    calls = 0

    @_stub_retry(_ListeningSource(), max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "502 bad gateway"
            raise RuntimeError(msg)
        return "ok"

    assert fn() == "ok"
    assert notices == []


def test_not_found_error_does_not_retry() -> None:
    """A NOT_FOUND verdict is terminal: no replay, no sleeps."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0
    msg = "Resource not found"

    @_stub_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _NotFoundError(msg)

    with pytest.raises(_NotFoundError):
        fn()
    assert calls == 1
    assert sleeps == []


def test_lookup_error_does_not_retry() -> None:
    """'issue N not found' is permanent — retrying burns budget for nothing."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0
    msg = "metron: issue 999999 not found"

    @with_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise LookupError(msg)

    with pytest.raises(LookupError):
        fn()
    assert calls == 1
    assert sleeps == []


def test_instance_retry_sleep_overrides_decorator_sleep() -> None:
    """A retry_sleep attribute on the instance wins over the bound sleep."""
    decorator_sleeps, decorator_sleep = _capture_sleeps()
    instance_sleeps: list[float] = []

    class _Source:
        def __init__(self) -> None:
            self.retry_sleep = instance_sleeps.append
            self.calls = 0

        @with_retry(max_retries=2, sleep=decorator_sleep)
        def fetch(self) -> str:
            self.calls += 1
            if self.calls == 1:
                msg = "transient"
                raise RuntimeError(msg)
            return "ok"

    source = _Source()
    assert source.fetch() == "ok"
    assert decorator_sleeps == []
    assert instance_sleeps == [1.0]


def test_instance_retry_sleep_can_abort_the_retry_loop() -> None:
    """A raising retry_sleep (cancelled session) propagates immediately."""

    class _CancelledError(Exception):
        pass

    def cancelled_sleep(_delay: float) -> None:
        raise _CancelledError

    class _Source:
        def __init__(self) -> None:
            self.retry_sleep = cancelled_sleep
            self.calls = 0

        @with_retry(max_retries=5)
        def fetch(self) -> str:
            self.calls += 1
            msg = "transient"
            raise RuntimeError(msg)

    source = _Source()
    with pytest.raises(_CancelledError):
        source.fetch()
    assert source.calls == 1


def test_generic_delay_caps_at_60s() -> None:
    """Non-rate-limit retries cap at 60s/attempt regardless of attempt count."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(max_retries=10, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        msg = "transient"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError):
        fn()
    # Schedule: 1, 2, 4, 8, 16, 32, 60, 60, 60, 60.
    assert max(sleeps) <= 60.0


def test_module_not_found_does_not_retry() -> None:
    """Programmer errors (incl. bad imports) should raise immediately."""
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0
    msg = "No module named 'nonexistent'"

    @with_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise ModuleNotFoundError(msg)

    with pytest.raises(ModuleNotFoundError):
        fn()
    assert calls == 1
    assert sleeps == []


def test_type_error_does_not_retry() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        msg = "bad arg"
        raise TypeError(msg)

    with pytest.raises(TypeError):
        fn()
    assert calls == 1
    assert sleeps == []


def test_mixed_failures_track_budgets_independently() -> None:
    """
    Rate-limit and generic attempt counters advance independently.

    A retriable 5xx burst followed by a rate-limit hit should each draw
    from their own budget, not exhaust each other.
    """
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(max_retries=3, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "transient"
            raise RuntimeError(msg)  # generic attempt 0
        if calls == 2:
            raise _RateLimitedError  # rate-limit attempt 0
        if calls == 3:
            msg = "transient"
            raise RuntimeError(msg)  # generic attempt 1
        return "ok"

    assert fn() == "ok"
    assert calls == 4
    # Sleeps observed: generic 0 (1s), rate-limit 0 (30s), generic 1 (2s).
    assert sleeps == [1.0, _RATE_LIMIT_SCHEDULE[0], 2.0]


def test_simyan_client_cap_timeout_uses_rate_limit_schedule() -> None:
    """
    Simyan 3.x client-side cap exhaustion routes to the rate-limit schedule.

    When the bounded in-limiter wait expires, requests_ratelimiter raises
    Timeout("Rate limit not cleared within max_delay=...") and simyan
    wraps it in ServiceError("Service took too long to respond"). That is
    a rate-limit condition — the generic 31s budget can't outlast an
    hourly cap. Uses the real simyan/requests classes AND the real
    ComicVine classifier to pin the shape end-to-end.
    """
    from requests.exceptions import Timeout
    from simyan.errors import ServiceError

    from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource

    class _ComicVineStub(_StubSource):
        classify_retry_exception = staticmethod(
            ComicVineOnlineSource.classify_retry_exception
        )

    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(source=_ComicVineStub(), max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "Service took too long to respond"
            cause = "Rate limit not cleared within max_delay=40.0s"
            raise ServiceError(msg) from Timeout(cause)
        return "ok"

    assert fn() == "ok"
    assert sleeps == [_RATE_LIMIT_SCHEDULE[0]]


def test_genuine_timeout_stays_on_generic_schedule() -> None:
    """A real HTTP timeout (same ServiceError text) is not a rate limit."""
    from requests.exceptions import Timeout
    from simyan.errors import ServiceError

    from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource

    class _ComicVineStub(_StubSource):
        classify_retry_exception = staticmethod(
            ComicVineOnlineSource.classify_retry_exception
        )

    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @_stub_retry(source=_ComicVineStub(), max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "Service took too long to respond"
            cause = (
                "HTTPSConnectionPool(host='comicvine.gamespot.com'): Read timed out."
            )
            raise ServiceError(msg) from Timeout(cause)
        return "ok"

    assert fn() == "ok"
    assert sleeps == [1.0]


def test_api_key_redacted_from_exception_chain() -> None:
    """
    The retry boundary scrubs `api_key=` values from chained messages.

    simyan 3.x sends the ComicVine key as a query param; requests embeds
    the full URL in the HTTPError that becomes `__cause__` of every
    simyan error. A full-traceback log of that chain must not print the
    key. Uses the real simyan/requests classes to pin the shape.
    """
    import traceback

    from requests.exceptions import HTTPError
    from simyan.errors import AuthenticationError

    @with_retry(max_retries=1, sleep=lambda _s: None)
    def fn() -> None:
        err = HTTPError(
            "401 Client Error: Unauthorized for url: "
            "https://comicvine.gamespot.com/api/issue/4000-1/"
            "?api_key=SECRETKEY123&format=json"
        )
        msg = "Invalid API Key"
        raise AuthenticationError(msg) from err

    with pytest.raises(AuthenticationError) as excinfo:
        fn()
    chain = "".join(traceback.format_exception(excinfo.value))
    assert "SECRETKEY123" not in chain
    assert "api_key=REDACTED" in chain


def test_api_key_redacted_inside_nested_exception_args() -> None:
    """Exception objects nested in args (ConnectionError style) are scrubbed."""
    import traceback

    from requests.exceptions import ConnectionError as RequestsConnectionError
    from simyan.errors import ServiceError

    @with_retry(max_retries=0, sleep=lambda _s: None)
    def fn() -> None:
        inner = OSError(
            "Max retries exceeded with url: /api/issues/?api_key=SECRETKEY123"
        )
        err = RequestsConnectionError(inner)
        msg = "Unable to connect to comicvine"
        raise ServiceError(msg) from err

    with pytest.raises(ServiceError) as excinfo:
        fn()
    chain = "".join(traceback.format_exception(excinfo.value))
    assert "SECRETKEY123" not in chain
    assert "api_key=REDACTED" in chain


# --- wall-clock ceiling -----------------------------------------------------


def test_total_wait_ceiling_stops_a_server_hint_loop() -> None:
    """
    An honored `retry_after` per attempt is otherwise unbounded in total.

    `_MAX_RETRY_AFTER_S` caps ONE hint at an hour; nothing capped the sum,
    so eight of them could park a worker for most of a day.
    """
    sleeps, fake_sleep = _capture_sleeps()

    @_stub_retry(max_retries=1, sleep=fake_sleep)
    def fn() -> str:
        raise _RateLimitedError(retry_after=3600.0)

    with pytest.raises(_RateLimitedError):
        fn()
    assert sum(sleeps) <= _MAX_TOTAL_WAIT_S
    # One 3600s hint exactly fills the ceiling; a second would breach it.
    assert len(sleeps) == 1


def test_total_wait_ceiling_is_configurable_per_call() -> None:
    """A tighter ceiling ends the loop sooner, without truncating a delay."""
    sleeps, fake_sleep = _capture_sleeps()

    @_stub_retry(max_retries=1, sleep=fake_sleep, max_wait_s=100.0)
    def fn() -> str:
        raise _RateLimitedError

    with pytest.raises(_RateLimitedError):
        fn()
    # 30 + 60 = 90 fits; the next scheduled delay (120) would breach 100,
    # so the loop ends rather than sleeping a shortened, useless wait.
    assert sleeps == [30.0, 60.0]


def test_ceiling_leaves_the_tuned_rate_limit_schedule_intact() -> None:
    """
    The default ceiling must not silently shorten `_RATE_LIMIT_SCHEDULE`.

    That schedule's 8-attempt tail was tuned against a `-j 8` rate-limit
    cascade; a ceiling below its 2910s total would undo that fix without
    anything failing.
    """
    assert sum(_RATE_LIMIT_SCHEDULE) <= _MAX_TOTAL_WAIT_S


# --- cancellable sleep is the default ---------------------------------------


def test_default_sleep_is_interruptible() -> None:
    """
    Every caller gets cancellable waits, not just OnlineSession.

    The waits here run to minutes, so an uninterruptible default made
    Ctrl-C look broken for CLI users and left a programmatic cancel with
    nothing to interrupt.
    """
    calls = 0

    @_stub_retry(max_retries=3)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _RateLimitedError

    request_cancel()
    try:
        with pytest.raises(OnlineLookupAbortedError):
            fn()
    finally:
        clear_cancel()
    # Cancelled during the first backoff, so the call is never replayed.
    assert calls == 1


def test_interruptible_sleep_returns_normally_when_not_cancelled() -> None:
    """With no cancel pending it is an ordinary (short) sleep."""
    clear_cancel()
    interruptible_sleep(0.001)


def test_instance_retry_sleep_still_overrides_the_new_default() -> None:
    """OnlineSession's per-instance cancellable sleep keeps winning."""
    sleeps, fake_sleep = _capture_sleeps()

    class _Source(_StubSource):
        retry_sleep = staticmethod(fake_sleep)

        @with_retry(max_retries=2)
        def fetch(self) -> str:
            raise _RateLimitedError

    request_cancel()
    try:
        with pytest.raises(_RateLimitedError):
            _Source().fetch()
    finally:
        clear_cancel()
    # The instance sleep ran instead of the cancelling default.
    assert sleeps
