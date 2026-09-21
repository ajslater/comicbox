"""
Lifecycle of the shared simyan client.

A `Comicvine` holds more than sockets: the response cache's sqlite
connection, one rate-limit bucket connection per endpoint pool, and
pyrate-limiter's leaker thread. Closing the session releases the first
and stops the last but leaves every bucket open -- and, by dropping the
references that had kept them alive, turns a silent leak into a
`ResourceWarning` apiece. These tests pin the whole close.
"""

from __future__ import annotations

import gc
import warnings
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from comicbox.config.online.settings import OnlineCacheSettings, OnlineSettings
from comicbox.formats.base.online.rate_limits import COMICVINE_DEFAULT_PER_HOUR
from comicbox.formats.comicvine_api import online_source as comicvine
from tests.util.online_client import build_comicvine_client, spend

if TYPE_CHECKING:
    from pathlib import Path


class _FakeBucket:
    """A bucket double that records the registry's state when it was closed."""

    def __init__(self) -> None:
        self.closed = 0
        self.registry: dict[str, Any] = {}
        self.registry_was_empty: bool | None = None

    def close(self) -> None:
        self.closed += 1
        self.registry_was_empty = not self.registry


class _StuckBucket(_FakeBucket):
    """A bucket double whose close fails, as a rearranged upstream might."""

    @override
    def close(self) -> None:
        super().close()
        msg = "no connection"
        raise RuntimeError(msg)


class _FakeSession:
    """A `CachedLimiterSession` double, down to `limiter.bucket_factory`."""

    def __init__(self, *buckets: _FakeBucket) -> None:
        self.closed = 0
        registry = {f"pool{i}": bucket for i, bucket in enumerate(buckets)}
        for bucket in buckets:
            bucket.registry = registry
        self.limiter = Namespace(bucket_factory=Namespace(buckets=registry))

    @property
    def registry(self) -> dict[str, Any]:
        """The bucket registry the factory serves lookups from."""
        return self.limiter.bucket_factory.buckets

    def close(self) -> None:
        self.closed += 1


class _FakeClient:
    """A `Comicvine` double: the session hangs off the same private name."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session


class _Unclosable:
    """A client double with neither a session nor a close, as fakes have."""


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own empty shared-client cache."""
    monkeypatch.setattr(comicvine, "_session_cache", {})


def _seed(client: Any, key: tuple[str, str] = ("key", "")) -> None:
    comicvine._session_cache[key] = (client, ())


def _buckets(client: Any) -> list[Any]:
    return list(client._session.limiter.bucket_factory.buckets.values())


def test_close_closes_every_shared_client() -> None:
    """One run, one close per credential set."""
    first = _FakeSession()
    second = _FakeSession()
    _seed(_FakeClient(first), ("key", ""))
    _seed(_FakeClient(second), ("other", "https://cv.example/api"))

    comicvine.close_shared_sessions()

    assert first.closed == 1
    assert second.closed == 1


def test_close_keeps_the_cache_entries() -> None:
    """
    A closed simyan client is still the right one to reuse.

    It reopens its response cache on demand and rebuilds a rate-limit
    bucket over the same file, so the credential set keeps its client.
    """
    _seed(_FakeClient(_FakeSession()))

    comicvine.close_shared_sessions()

    assert comicvine._session_cache


def test_close_tolerates_a_client_without_a_session() -> None:
    """Tests seed doubles; a missing `_session` must not break teardown."""
    _seed(_Unclosable())

    comicvine.close_shared_sessions()  # must not raise


def test_close_empties_the_registry_before_closing_the_buckets() -> None:
    """
    A closed bucket must never be handed back out.

    The factory serves its registry without checking, and a request that
    gets a closed bucket dies on its `None` connection, so the registry
    is emptied first: a racing lookup then builds a fresh bucket instead
    of finding this one mid-close.
    """
    bucket = _FakeBucket()
    session = _FakeSession(bucket)
    _seed(_FakeClient(session))

    comicvine.close_shared_sessions()

    assert bucket.closed == 1
    assert bucket.registry_was_empty is True
    assert not session.registry


def test_close_survives_a_bucket_that_will_not_close() -> None:
    """One bad bucket must not stop the rest, nor fail the caller."""
    stuck = _StuckBucket()
    fine = _FakeBucket()
    session = _FakeSession(stuck, fine)
    _seed(_FakeClient(session))

    comicvine.close_shared_sessions()

    assert stuck.closed == 1
    assert fine.closed == 1
    assert session.closed == 1


def test_a_closed_client_releases_every_sqlite_handle(tmp_path: Path) -> None:
    """
    The response cache's connection, and one per rate-limit pool.

    `session.close()` alone gets the first; the buckets are
    pyrate-limiter's and have to be closed by name (see
    `_close_limiter_buckets`).
    """
    client = build_comicvine_client(tmp_path)
    spend(client, "issues", 2)
    spend(client, "search", 1)
    buckets = _buckets(client)
    assert len(buckets) == 2
    assert all(bucket.conn is not None for bucket in buckets)

    comicvine.close_client(client)

    assert all(bucket.conn is None for bucket in buckets)
    assert client._session.cache.responses._connection is None


def test_a_closed_client_emits_no_resource_warning(tmp_path: Path) -> None:
    """The symptom that asked for this: unclosed sqlite handles."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = build_comicvine_client(tmp_path)
        spend(client, "issues", 1)
        spend(client, "search", 1)

        comicvine.close_client(client)

        del client
        gc.collect()

    leaked = [
        str(warning.message)
        for warning in caught
        if issubclass(warning.category, ResourceWarning)
    ]
    assert not leaked


def test_a_closed_client_is_still_usable(tmp_path: Path) -> None:
    """
    Not a cancel: the client works after a close, and remembers.

    The hourly budget lives in the bucket file, so the rebuilt bucket
    picks up where the closed one left off.
    """
    client = build_comicvine_client(tmp_path)
    spend(client, "issues", 3)

    comicvine.close_client(client)
    spend(client, "issues", 1)

    status = comicvine.shared_client_rate_limit_status(
        OnlineSettings(cache=OnlineCacheSettings(dir=tmp_path))
    )
    assert status["issues"]["remaining"] == COMICVINE_DEFAULT_PER_HOUR - 4
    comicvine.close_client(client)


def test_close_is_safe_to_repeat(tmp_path: Path) -> None:
    """A second close finds nothing to do rather than raising."""
    client = build_comicvine_client(tmp_path)
    spend(client, "issues", 1)

    comicvine.close_client(client)
    comicvine.close_client(client)  # must not raise


def test_the_runner_closes_shared_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished run releases what its Comic Vine lookups opened."""
    from comicbox.run import Runner

    calls: list[int] = []
    monkeypatch.setattr(comicvine, "close_shared_sessions", lambda: calls.append(1))
    comic = tmp_path / "file_0.cbz"
    comic.write_bytes(b"")  # zero-byte cbz; Comicbox will fail to open it
    runner = Runner(
        Namespace(comicbox=Namespace(paths=[str(comic)], print=Namespace(phases="p")))
    )

    runner.run()

    assert calls == [1]


def test_online_session_close_releases_both_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OnlineSession.close()` is not a Metron-only release."""
    from comicbox.formats.metron_api import online_source as metron
    from comicbox.online_session import OnlineCredentials, OnlineSession

    calls: list[str] = []
    monkeypatch.setattr(
        comicvine, "close_shared_sessions", lambda: calls.append("comicvine")
    )
    monkeypatch.setattr(metron, "close_shared_sessions", lambda: calls.append("metron"))
    credentials = OnlineCredentials(comicvine_key="k")

    with OnlineSession(sources={"comicvine"}, credentials=credentials):
        pass

    assert calls == ["metron", "comicvine"]
