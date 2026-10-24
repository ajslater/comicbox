"""
Lifecycle of the shared mokkari session.

A mokkari `Session` holds a pooled `requests.Session`, and its
`SqliteCache` a sqlite connection that `Session.close()` leaves open.
That makes two things comicbox's business: releasing both at the end of
a run, and not letting a forked child inherit them.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.config.online.settings import (
    CacheMode,
    OnlineCacheSettings,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.metron_api import online_source as metron
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.metron_api.paced_session import GateRateLimiter

if TYPE_CHECKING:
    from pathlib import Path


class _Closable:
    """A session or cache double that records having been closed."""

    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _ClosableSession(_Closable):
    """A session double with a closable cache, as a real Session has."""

    def __init__(self) -> None:
        super().__init__()
        self.cache = _Closable()


class _UncloseableSession:
    """A session double with no `close`, as older test fakes have."""


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own empty module-level session and gate caches."""
    monkeypatch.setattr(metron, "_session_cache", {})
    monkeypatch.setattr(metron, "_gate_cache", {})


def _seed(session: Any, key: str = "k") -> None:
    metron._session_cache[key] = (session, ())
    metron._gate_cache[key] = RateGate(default_limit=20)


def test_close_closes_every_shared_session() -> None:
    """One run, one close per token, of the session and of its cache."""
    first = _ClosableSession()
    second = _ClosableSession()
    _seed(first, "k1")
    _seed(second, "k2")

    metron.close_shared_sessions()

    assert first.closed == 1
    assert second.closed == 1
    assert first.cache.closed == 1
    assert second.cache.closed == 1


def test_close_keeps_the_cache_entries() -> None:
    """
    A closed mokkari Session is still the right one to reuse.

    It reopens connections on demand, and the gate and
    `rate_limit_status` it carries are still this token's.
    """
    session = _ClosableSession()
    _seed(session)

    metron.close_shared_sessions()

    assert metron._session_cache
    assert metron._gate_cache


def test_close_tolerates_a_double_without_close() -> None:
    """Tests seed fakes; a missing `close` must not break the teardown."""
    _seed(_UncloseableSession())

    metron.close_shared_sessions()  # must not raise


def test_reset_drops_sessions_and_gates() -> None:
    """The test seam clears both caches, not just the sessions."""
    _seed(_ClosableSession())

    metron.reset_shared_sessions()

    assert not metron._session_cache
    assert not metron._gate_cache


def test_the_fork_handler_empties_both_caches_and_rebinds_the_lock() -> None:
    """
    A child must not inherit the parent's pooled sockets.

    The lock is rebound rather than taken: the thread that held it at the
    instant of the fork does not exist in the child, so acquiring it
    would deadlock forever.
    """
    _seed(_ClosableSession())
    before = metron._session_cache_lock

    metron._after_fork_in_child()

    assert not metron._session_cache
    assert not metron._gate_cache
    assert metron._session_cache_lock is not before


def test_the_fork_handler_does_not_close_inherited_sockets() -> None:
    """Closing them in the child would break the parent's own connections."""
    session = _ClosableSession()
    _seed(session)

    metron._after_fork_in_child()

    assert session.closed == 0


def test_build_session_registers_the_gate_as_the_rate_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate reaches mokkari through the public hook, not a subclass."""
    settings = OnlineSettings(cache=OnlineCacheSettings(mode=CacheMode.OFF))
    src = MetronOnlineSource(
        OnlineSourceCredentials(key="t"),
        settings,
    )

    session = src._get_session()
    gate: RateGate | None = src._gate()

    assert isinstance(session.rate_limiter, GateRateLimiter)
    assert session.rate_limiter._gate is gate
    session.close()


def test_the_runner_closes_shared_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished run releases the pooled connections it opened."""
    from comicbox.run import Runner

    calls: list[int] = []
    monkeypatch.setattr(metron, "close_shared_sessions", lambda: calls.append(1))
    comic = tmp_path / "file_0.cbz"
    comic.write_bytes(b"")  # zero-byte cbz; Comicbox will fail to open it
    runner = Runner(
        Namespace(comicbox=Namespace(paths=[str(comic)], print=Namespace(phases="p")))
    )

    runner.run()

    assert calls == [1]


def test_online_session_close_releases_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OnlineSession.close()` and its context manager both release."""
    from comicbox.online_session import OnlineCredentials, OnlineSession

    calls: list[int] = []
    monkeypatch.setattr(metron, "close_shared_sessions", lambda: calls.append(1))
    credentials = OnlineCredentials(metron_key="k")

    OnlineSession(sources={"metron"}, credentials=credentials).close()
    assert calls == [1]

    with OnlineSession(sources={"metron"}, credentials=credentials):
        pass
    assert calls == [1, 1]
