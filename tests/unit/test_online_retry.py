"""Retry decorator tests."""

from __future__ import annotations

import pytest

from comicbox.online.retry import with_retry


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


def test_retries_then_succeeds() -> None:
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
    # Two sleeps before the third successful call: 1s, 2s.
    assert sleeps == [1.0, 2.0]


def test_honors_retry_after_hint() -> None:
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
    assert sleeps == [12.5]


def test_max_retries_exhausted_raises() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(max_retries=2, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _FakeRateLimitError

    with pytest.raises(Exception, match="rate limited"):
        fn()
    # max_retries=2 means 1 + 2 attempts = 3, with 2 sleeps in between.
    assert calls == 3
    assert sleeps == [1.0, 2.0]


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


def test_delay_caps_at_60s() -> None:
    sleeps, fake_sleep = _capture_sleeps()
    calls = 0

    @with_retry(max_retries=10, sleep=fake_sleep)
    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _FakeRateLimitError

    with pytest.raises(_FakeRateLimitError):
        fn()
    # Schedule: 1, 2, 4, 8, 16, 32, 60, 60, 60, 60.
    assert max(sleeps) <= 60.0
