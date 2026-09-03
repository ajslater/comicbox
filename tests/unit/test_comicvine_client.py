"""ComicVine client construction and error classification tests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from requests.exceptions import Timeout
from simyan.errors import AuthenticationError, RateLimitError, ServiceError

from comicbox.config.online.settings import (
    CacheMode,
    OnlineCacheSettings,
    OnlineSettings,
    OnlineSourceCredentials,
    OnlineSourceLimits,
    OnlineSourceTuning,
    OnlineTuningSettings,
)
from comicbox.formats.base.online.retry import RetryCategory, with_retry
from comicbox.formats.comicvine_api.online_source import (
    ComicVineOnlineSource,
    reset_shared_sessions,
)
from comicbox.version import USER_AGENT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        # Typed by simyan from the HTTP status...
        (RateLimitError(None), RetryCategory.RATE_LIMIT),
        (AuthenticationError("Invalid API Key"), RetryCategory.AUTH),
        # ...and from Comic Vine's HTTP-200 body `status_code` (107, 100).
        (RateLimitError("Rate Limit Exceeded"), RetryCategory.RATE_LIMIT),
        # Body errors simyan leaves as a plain ServiceError: CV 101, 102, 104.
        (ServiceError("Object Not Found"), RetryCategory.NOT_FOUND),
        (ServiceError("Error in URL Format"), RetryCategory.INVALID),
        (ServiceError("Filter Error"), RetryCategory.INVALID),
        # simyan's own wording for an HTTP 404.
        (ServiceError("Resource not found"), RetryCategory.NOT_FOUND),
        # Unrecognized bodies stay retriable rather than failing a lookup.
        (ServiceError("Something new upstream"), RetryCategory.TRANSIENT),
        (ServiceError(None), RetryCategory.TRANSIENT),
    ],
)
def test_classify_by_exception_type_and_body_message(
    exc: BaseException, expected: RetryCategory
) -> None:
    """
    Simyan 4 types the two retry-relevant failures; the rest read as messages.

    RateLimitError on HTTP 429/420 and CV body status 107,
    AuthenticationError on HTTP 401 and body status 100. Comic Vine's
    other body errors arrive as a bare ServiceError carrying only the
    body's `error` string, so the message is the only signal left.
    """
    assert ComicVineOnlineSource.classify_retry_exception(exc) is expected


def test_classify_client_side_cap_timeout_is_rate_limit() -> None:
    """
    Client-side rate-limit cap exhaustion is only visible in __cause__.

    The ServiceError message is the generic "Service took too long to
    respond"; the chained requests Timeout carries the rate-limit text.
    """
    exc = ServiceError("Service took too long to respond")
    exc.__cause__ = Timeout("Rate limit not cleared within max_delay=40.0s")
    assert (
        ComicVineOnlineSource.classify_retry_exception(exc) is RetryCategory.RATE_LIMIT
    )


def test_classify_genuine_read_timeout_is_transient() -> None:
    """The same ServiceError with a plain read timeout cause stays generic."""
    exc = ServiceError("Service took too long to respond")
    exc.__cause__ = Timeout(
        "HTTPSConnectionPool(host='comicvine.gamespot.com', port=443): Read timed out."
    )
    assert (
        ComicVineOnlineSource.classify_retry_exception(exc) is RetryCategory.TRANSIENT
    )


@pytest.mark.parametrize(
    "exc",
    [
        # CV 102/104: comicbox built a bad url or filter expression.
        # Replaying it verbatim can only fail identically, which is the
        # point of INVALID over TRANSIENT.
        ServiceError("Filter Error"),
        ServiceError("Error in URL Format"),
        # CV 100 / HTTP 401: burning the generic 5-attempt budget on a
        # key that will never work just delays the failure ~31s.
        AuthenticationError("Invalid API Key"),
        # CV 101 / HTTP 404.
        ServiceError("Object Not Found"),
    ],
)
def test_terminal_failures_are_called_exactly_once(exc: BaseException) -> None:
    """A terminal classification must not be replayed by the retry loop."""
    calls = {"n": 0}

    class _Source:
        classify_retry_exception = staticmethod(
            ComicVineOnlineSource.classify_retry_exception
        )

        @with_retry()
        def call(self) -> None:
            calls["n"] += 1
            raise exc

    with pytest.raises(type(exc)):
        _Source().call()
    assert calls["n"] == 1


def _unparseable_body_error(status: int) -> ServiceError:
    """
    Build the ServiceError simyan raises when an error body isn't JSON.

    simyan parses the body inside its `except HTTPError` block, and the
    inner `except JSONDecodeError as err` rebinds the cause — so the
    HTTPError (and its status) is gone, and requests' JSONDecodeError
    carries no response. The status survives only as the message prefix.
    """
    from requests.exceptions import JSONDecodeError

    exc = ServiceError(
        f"{status}: Unable to parse response from "
        "'https://comicvine.gamespot.com/api/issues/' as Json"
    )
    exc.__cause__ = JSONDecodeError("Expecting value", "<html>", 0)
    return exc


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, RetryCategory.AUTH),
        (404, RetryCategory.NOT_FOUND),
        (420, RetryCategory.RATE_LIMIT),
        (429, RetryCategory.RATE_LIMIT),
        (503, RetryCategory.TRANSIENT),
    ],
)
def test_classify_unparseable_error_body_by_status(
    status: int, expected: RetryCategory
) -> None:
    """
    An HTML- or empty-bodied error keeps its status through the message.

    Without this, an edge-served 429 looks like a plain server error: it
    would take the generic 31s budget instead of the rate-limit schedule
    and never fire the `on_rate_limit` notice.
    """
    exc = _unparseable_body_error(status)
    assert ComicVineOnlineSource.classify_retry_exception(exc) is expected


def test_classify_404_from_chained_response_status() -> None:
    """Simyan's parseable-body 404 is caught by the chained response."""
    from requests import Response
    from requests.exceptions import HTTPError

    response = Response()
    response.status_code = 404
    cause = HTTPError("404 Client Error", response=response)
    exc = ServiceError("Resource not found")
    exc.__cause__ = cause
    assert (
        ComicVineOnlineSource.classify_retry_exception(exc) is RetryCategory.NOT_FOUND
    )


def test_classify_server_error_is_transient() -> None:
    exc = ServiceError("500: {'error': 'Internal Server Error'}")
    assert (
        ComicVineOnlineSource.classify_retry_exception(exc) is RetryCategory.TRANSIENT
    )


def test_classify_non_simyan_exception_is_unclaimed() -> None:
    """Anything outside simyan's hierarchy returns None (decorator fallback)."""
    exc = RuntimeError("connection reset by peer")
    assert ComicVineOnlineSource.classify_retry_exception(exc) is None


# ------------------------------------------------------- client construction


class _FakeComicvine:
    """Captures simyan constructor kwargs; stands in for the client."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.cache_deletes: list[dict] = []
        self._session = SimpleNamespace(
            cache=SimpleNamespace(delete=lambda **kw: self.cache_deletes.append(kw)),
        )


def _make_cache_settings(
    tmp_path: Path,
    mode: CacheMode = CacheMode.ON,
    ttl: timedelta | None = None,
) -> OnlineSettings:
    if ttl is None:
        ttl = timedelta(days=7)
    cache = OnlineCacheSettings(mode=mode, dir=tmp_path, ttl=ttl)
    return OnlineSettings(cache=cache)


def _build_with_fake(
    monkeypatch: pytest.MonkeyPatch, settings: OnlineSettings
) -> _FakeComicvine:
    creds = OnlineSourceCredentials(key="test-key")
    src = ComicVineOnlineSource(creds, settings)
    monkeypatch.setattr("simyan.comicvine.Comicvine", _FakeComicvine)
    client = src._build_session()
    assert isinstance(client, _FakeComicvine)
    return client


def test_get_session_memoizes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream client is built once per source lifetime, then reused."""
    creds = OnlineSourceCredentials(key="test-key")
    settings = OnlineSettings()
    src = ComicVineOnlineSource(creds, settings)
    builds = {"n": 0}

    def fake_build() -> object:
        builds["n"] += 1
        return object()

    monkeypatch.setattr(src, "_build_session", fake_build)
    first = src._get_session()
    second = src._get_session()
    assert first is second
    assert builds["n"] == 1


def test_build_session_passes_simyan_kwargs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cache and rate-limit files land in comicbox's cache dir, ttl → expiry."""
    settings = _make_cache_settings(tmp_path)
    client = _build_with_fake(monkeypatch, settings)
    kw = client.kwargs
    assert kw["api_key"] == "test-key"
    assert kw["user_agent"] == USER_AGENT
    assert kw["cache_path"] == tmp_path / "comicvine_cache.sqlite"
    assert kw["ratelimit_path"] == tmp_path / "comicvine_rate_limit.sqlite"
    assert kw["cache_expiry"] == timedelta(days=7)  # ttl flows through as-is
    assert "base_url" not in kw  # no creds.url set
    # v2 kwargs must be gone.
    assert "cache" not in kw
    assert "limiter" not in kw


def test_build_session_cache_off_uses_do_not_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    OFF pins cache_path (never ~/.cache/simyan) and passes DO_NOT_CACHE.

    That flag is the whole of OFF now: simyan stopped passing
    `cache_control`, so no response can talk its way back into the cache
    on its own headers. See `_cache_expiry`.
    """
    from requests_cache import DO_NOT_CACHE

    settings = _make_cache_settings(tmp_path, mode=CacheMode.OFF)
    client = _build_with_fake(monkeypatch, settings)
    assert client.kwargs["cache_expiry"] == DO_NOT_CACHE
    assert client.kwargs["cache_path"] == tmp_path / "comicvine_cache.sqlite"


def test_build_session_zero_ttl_never_expires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from requests_cache import NEVER_EXPIRE

    settings = _make_cache_settings(tmp_path, ttl=timedelta(0))
    client = _build_with_fake(monkeypatch, settings)
    assert client.kwargs["cache_expiry"] == NEVER_EXPIRE


def test_build_session_maintains_cache_once_per_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The expired-row purge runs once per process per cache file."""
    cache_path = tmp_path / "comicvine_cache.sqlite"
    with closing(sqlite3.connect(cache_path)) as conn:
        conn.execute("CREATE TABLE t (x)")
        conn.commit()

    settings = _make_cache_settings(tmp_path)
    first = _build_with_fake(monkeypatch, settings)
    assert first.cache_deletes == [{"expired": True, "vacuum": False}]
    # A second source over the same cache file skips the housekeeping.
    second = _build_with_fake(monkeypatch, settings)
    assert second.cache_deletes == []


def test_build_session_drops_v2_queries_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Simyan v2's `queries` table is dropped from the shared cache file."""
    cache_path = tmp_path / "comicvine_cache.sqlite"
    with closing(sqlite3.connect(cache_path)) as conn:
        conn.execute("CREATE TABLE queries (query, response, query_date)")
        conn.commit()

    settings = _make_cache_settings(tmp_path)
    _build_with_fake(monkeypatch, settings)

    with closing(sqlite3.connect(cache_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "queries" not in tables


def test_get_session_warns_on_ignored_rate_limit_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    CV per_second/per_hour overrides can't flow into simyan — warn.

    Driven through `_get_session`, not `_build_session`: the warning
    deliberately fires on every source that carries the ignored config,
    not only on the one that wins the shared-client cache miss.
    """
    from loguru import logger as loguru_logger

    reset_shared_sessions()
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        tuning = OnlineTuningSettings(
            per_source={
                "comicvine": OnlineSourceTuning(
                    rate_limit=OnlineSourceLimits(per_second=2)
                )
            }
        )
        settings = OnlineSettings(
            cache=OnlineCacheSettings(dir=tmp_path), tuning=tuning
        )
        monkeypatch.setattr("simyan.comicvine.Comicvine", _FakeComicvine)
        creds = OnlineSourceCredentials(key="warn-key")
        ComicVineOnlineSource(creds, settings)._get_session()
    finally:
        loguru_logger.remove(handler_id)
        reset_shared_sessions()
    assert any("ignored" in message for message in messages)


def test_get_session_shared_across_source_instances(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Same credentials → one client, even across separately built sources.

    `_build_active_online_sources` rebuilds sources per file, so this is
    what keeps a batch from paying for a fresh simyan client (and its
    connection pool and sqlite handles) per comic.
    """
    reset_shared_sessions()
    try:
        monkeypatch.setattr("simyan.comicvine.Comicvine", _FakeComicvine)
        settings = _make_cache_settings(tmp_path)
        creds = OnlineSourceCredentials(key="shared-key")
        first = ComicVineOnlineSource(creds, settings)._get_session()
        second = ComicVineOnlineSource(creds, settings)._get_session()
        assert first is second
    finally:
        reset_shared_sessions()


def test_get_session_not_shared_across_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A different api_key gets its own client."""
    reset_shared_sessions()
    try:
        monkeypatch.setattr("simyan.comicvine.Comicvine", _FakeComicvine)
        settings = _make_cache_settings(tmp_path)
        first = ComicVineOnlineSource(
            OnlineSourceCredentials(key="key-a"), settings
        )._get_session()
        second = ComicVineOnlineSource(
            OnlineSourceCredentials(key="key-b"), settings
        )._get_session()
        assert first is not second
    finally:
        reset_shared_sessions()


def test_get_session_warns_when_reused_with_different_cache_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """First build wins; the loser is told its cache config is ignored."""
    from loguru import logger as loguru_logger

    reset_shared_sessions()
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        monkeypatch.setattr("simyan.comicvine.Comicvine", _FakeComicvine)
        creds = OnlineSourceCredentials(key="mismatch-key")
        ComicVineOnlineSource(creds, _make_cache_settings(tmp_path))._get_session()
        other = tmp_path / "other"
        other.mkdir()
        ComicVineOnlineSource(creds, _make_cache_settings(other))._get_session()
    finally:
        loguru_logger.remove(handler_id)
        reset_shared_sessions()
    assert any("ignored in favor of" in message for message in messages)
