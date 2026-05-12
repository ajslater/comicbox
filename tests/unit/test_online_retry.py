"""Retry decorator tests."""

from __future__ import annotations

import pytest

from comicbox.online.retry import _RATE_LIMIT_SCHEDULE, with_retry


class _FakeRateLimitError(Exception):
    def __init__(
        self, msg: str = "rate limited", retry_after: float | None = None
    ) -> None:
        super().__init__(msg)
        self.retry_after = retry_after


# Match what mokkari raises by name (the retry decorator key off the class name).
_FakeRateLimitError.__name__ = "RateLimitError"


class _FakeAuthError(Exception):
    pass


_FakeAuthError.__name__ = "AuthenticationError"


def _capture_sleeps() -> tuple[list[float], callable]:
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

    @with_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _FakeRateLimitError
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

    @with_retry(sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _FakeRateLimitError(retry_after=12.5)
        return "ok"

    fn()
    # Hint wins over our 30s default first slot.
    assert sleeps == [12.5]


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

    @with_retry(max_retries=1, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _FakeRateLimitError

    with pytest.raises(_FakeRateLimitError):
        fn()
    # 1 + len(_RATE_LIMIT_SCHEDULE) attempts, with len(schedule) sleeps.
    assert calls == 1 + len(_RATE_LIMIT_SCHEDULE)
    assert sleeps == list(_RATE_LIMIT_SCHEDULE)


def test_auth_error_does_not_retry() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0
    msg = "401 unauthorized"

    @with_retry(max_retries=5, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _FakeAuthError(msg)

    with pytest.raises(_FakeAuthError):
        fn()
    assert calls == 1
    assert sleeps == []


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

    @with_retry(max_retries=3, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "transient"
            raise RuntimeError(msg)  # generic attempt 0
        if calls == 2:
            raise _FakeRateLimitError  # rate-limit attempt 0
        if calls == 3:
            msg = "transient"
            raise RuntimeError(msg)  # generic attempt 1
        return "ok"

    assert fn() == "ok"
    assert calls == 4
    # Sleeps observed: generic 0 (1s), rate-limit 0 (30s), generic 1 (2s).
    assert sleeps == [1.0, _RATE_LIMIT_SCHEDULE[0], 2.0]
