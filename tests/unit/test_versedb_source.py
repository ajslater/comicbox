"""VerseDBOnlineSource: search shape, filters, fast paths, cache modes, lifecycle."""

from __future__ import annotations

import gc
import warnings
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from comicbox.config.online.settings import (
    CacheMode,
    OnlineCacheSettings,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.base.online.retry import RetryCategory
from comicbox.formats.versedb_api import client as client_module
from comicbox.formats.versedb_api import online_source
from comicbox.formats.versedb_api.online_source import (
    VerseDBOnlineSource,
    close_shared_sessions,
    shared_client_rate_limit_status,
)
from tests.util.versedb_transport import (
    Reply,
    VerseDBTransport,
    fixture,
    recorded_reply,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_BLADEHAWK = 139382
_PROFILE = ComicProfile(series="Absolute Bladehawk", issue="1", year=2024)


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> VerseDBTransport:
    """Send every new client through the recordings."""
    mock = VerseDBTransport()
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    return mock


def _source(
    tmp_path: Path,
    *,
    key: str = "token",
    mode: CacheMode = CacheMode.ON,
    series_ids: dict[str, int] | None = None,
) -> VerseDBOnlineSource:
    settings = OnlineSettings(
        lookup=OnlineLookupSettings(series_ids=series_ids or {}),
        cache=OnlineCacheSettings(mode=mode, dir=tmp_path),
    )
    return VerseDBOnlineSource(OnlineSourceCredentials(key=key), settings)


def _with_series_rows(rows: list[dict[str, Any]]) -> Callable[[httpx.Request], Reply]:
    """Answer from the recordings, but with these series-search rows."""

    def reply_for(request: httpx.Request) -> Reply:
        if request.url.path == "/api/v1/series":
            payload = fixture("series_search")
            payload["data"] = rows
            return Reply(payload)
        return recorded_reply(request)

    return reply_for


def _series_row(series_id: int, name: str, start_year: int = 2024) -> dict[str, Any]:
    row = dict(fixture("series_search")["data"][0])
    return {**row, "id": series_id, "name": name, "start_year": start_year}


# -- search ---------------------------------------------------------------


def test_search_spends_two_calls_and_finds_the_issue(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    """One series search and ONE issue list across every kept series."""
    candidates = _source(tmp_path).search(_PROFILE)
    assert transport.paths == ["/api/v1/series", "/api/v1/issues"]
    assert [c.issue_id for c in candidates] == [55684]
    params = transport.params()
    assert params["q"] == "1"
    assert params["include"] == "series"
    assert str(_BLADEHAWK) in params["series_ids"].split(",")


def test_candidate_carries_the_series_detail_and_real_link(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    (candidate,) = _source(tmp_path).search(_PROFILE)
    summary = candidate.summary
    assert (candidate.source, candidate.volume_id, candidate.url) == (
        "versedb",
        _BLADEHAWK,
        "https://versedb.com/issue/55684/the-zoo-part-one",
    )
    assert {
        "series": summary.series,
        "issue": summary.issue,
        "year": summary.year,
        "series_publisher": summary.series_publisher,
        "series_start_year": summary.series_start_year,
        "issue_title": summary.issue_title,
        # Scored fields stay unset until a calibration says otherwise.
        "publisher": summary.publisher,
    } == {
        "series": "Absolute Bladehawk",
        "issue": "1",
        "year": 2024,
        "series_publisher": "DC Comics",
        "series_start_year": 2024,
        "issue_title": "The Zoo, Part One",
        "publisher": None,
    }
    assert (summary.cover_url or "").endswith("thumb.webp")
    assert (summary.cover_url_full or "").endswith("cover_lg.webp")


def test_a_series_that_began_after_the_comic_is_not_queried(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    """Absolute Bladehawk (2026) can't hold a 2024 comic."""
    _source(tmp_path).search(_PROFILE)
    assert "243748" not in transport.params()["series_ids"].split(",")


def test_a_dissimilar_series_name_is_not_queried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mock = VerseDBTransport(
        _with_series_rows(
            [
                _series_row(_BLADEHAWK, "Absolute Bladehawk"),
                _series_row(1, "Gardening Weekly"),
            ]
        )
    )
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    _source(tmp_path).search(_PROFILE)
    assert mock.params()["series_ids"] == str(_BLADEHAWK)


def test_no_surviving_series_spends_no_issue_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mock = VerseDBTransport(_with_series_rows([_series_row(1, "Gardening Weekly")]))
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    assert _source(tmp_path).search(_PROFILE) == []
    assert mock.paths == ["/api/v1/series"]


def test_only_the_exact_number_is_a_candidate(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    """The server's q="1" also returns 10 to 19; none of them is #1."""
    source = _source(tmp_path, series_ids={"versedb": 165850})
    candidates = source.search(_PROFILE)
    # G.I. Joe (1951) numbers its first issue "1 [10]".
    assert [c.summary.issue for c in candidates] == ["1 [10]"]


def test_series_id_skips_discovery(transport: VerseDBTransport, tmp_path: Path) -> None:
    candidates = _source(tmp_path, series_ids={"versedb": _BLADEHAWK}).search(_PROFILE)
    assert transport.paths == ["/api/v1/issues"]
    assert transport.params()["series_ids"] == str(_BLADEHAWK)
    assert [c.issue_id for c in candidates] == [55684]


def test_no_series_name_no_request(transport: VerseDBTransport, tmp_path: Path) -> None:
    assert _source(tmp_path).search(ComicProfile(issue="1")) == []
    assert transport.requests == []


def _paged(pages: list[list[str]]) -> Callable[[httpx.Request], Reply]:
    """Issue-list pages whose rows carry these issue numbers."""
    template = fixture("list_issues")["data"][0]

    def reply_for(request: httpx.Request) -> Reply:
        if request.url.path != "/api/v1/issues":
            return recorded_reply(request)
        page = int(request.url.params["page"])
        payload = fixture("list_issues")
        payload["data"] = [
            {**template, "id": page * 100 + i, "issue_number": number}
            for i, number in enumerate(pages[page - 1])
        ]
        payload["meta"]["last_page"] = len(pages)
        return Reply(payload)

    return reply_for


@pytest.mark.parametrize(
    ("pages", "calls", "found"),
    [
        # A page ending in a non-match: exact matches rank first, so stop.
        ([["1", "10"], ["1"]], 1, 1),
        # A page that is still matching at its end may continue.
        ([["1", "1"], ["1", "12"]], 2, 3),
        # Never past the cap.
        ([["1"], ["1"], ["1"], ["1"]], 3, 3),
    ],
)
def test_paging_stops_once_matches_run_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pages: list[list[str]],
    calls: int,
    found: int,
) -> None:
    mock = VerseDBTransport(_paged(pages))
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    candidates = _source(tmp_path, series_ids={"versedb": _BLADEHAWK}).search(_PROFILE)
    assert mock.paths.count("/api/v1/issues") == calls
    assert len(candidates) == found


def test_a_numberless_comic_gets_one_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mock = VerseDBTransport(_paged([["1", "2"], ["3"]]))
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    source = _source(tmp_path, series_ids={"versedb": _BLADEHAWK})
    candidates = source.search(ComicProfile(series="Absolute Bladehawk"))
    assert mock.paths == ["/api/v1/issues"]
    assert "q" not in mock.params()
    assert len(candidates) == 2


# -- get, lookup, probe ---------------------------------------------------


def test_get_returns_the_issue_detail(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    data = _source(tmp_path).get(1215061)
    assert data["id"] == 1215061
    assert data["series"]["name"] == "Absolute Bladehawk"
    assert transport.paths == ["/api/v1/issues/1215061"]


def test_get_does_not_retry_a_404(transport: VerseDBTransport, tmp_path: Path) -> None:
    with pytest.raises(client_module.VerseDBNotFoundError):
        _source(tmp_path).get(999999999)
    assert len(transport.requests) == 1


def test_get_waits_out_a_429(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    replies = iter(
        (Reply({"message": "x"}, status=429, headers={"Retry-After": "0.01"}),)
    )
    mock = VerseDBTransport(
        lambda request: next(replies, None) or recorded_reply(request)
    )
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)
    assert _source(tmp_path).get(1)["id"] == 1
    assert len(mock.requests) == 2


def test_lookup_issue_is_one_call(transport: VerseDBTransport, tmp_path: Path) -> None:
    candidate = _source(tmp_path).lookup_issue(_BLADEHAWK, "001")
    assert candidate is not None
    assert candidate.issue_id == 55684
    assert transport.paths == ["/api/v1/issues"]
    assert transport.params()["q"] == "1"


def test_lookup_issue_without_a_number_sends_nothing(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    assert _source(tmp_path).lookup_issue(_BLADEHAWK, None) is None
    assert transport.requests == []


def test_probe_uses_a_private_uncached_client(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    source = _source(tmp_path)
    assert source.probe() == {
        "hour": {"limit": 300, "remaining": 299, "reset_epoch": None}
    }
    source.probe()
    assert len(transport.requests) == 2
    assert not (tmp_path / "versedb_cache.sqlite").exists()
    # The shared client was never built.
    assert shared_client_rate_limit_status("token") == {}


def test_shared_client_budget_after_a_request(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    _source(tmp_path).get(1)
    assert shared_client_rate_limit_status("token")["hour"]["remaining"] == 299
    assert shared_client_rate_limit_status("other") == {}


def test_is_configured_needs_a_token(tmp_path: Path) -> None:
    assert _source(tmp_path).is_configured()
    assert not _source(tmp_path, key="").is_configured()


# -- classification -------------------------------------------------------


def _subclasses(cls: type[BaseException]) -> set[type[BaseException]]:
    found = set(cls.__subclasses__())
    for sub in list(found):
        found |= _subclasses(sub)
    return found


def test_every_adapter_exception_is_classified() -> None:
    """An unclassified vendor exception would be silently retried."""
    for exc_class in {client_module.VerseDBError} | _subclasses(
        client_module.VerseDBError
    ):
        if exc_class is client_module.VerseDBError:
            continue
        # Built bare: only the class is under test, not its arguments.
        exc = exc_class.__new__(exc_class)
        assert VerseDBOnlineSource.classify_retry_exception(exc) is not None, exc_class


@pytest.mark.parametrize(
    ("exc", "category"),
    [
        (client_module.VerseDBQuotaError("x", 0.0), RetryCategory.QUOTA),
        (client_module.VerseDBRateLimitError("x", 1.0), RetryCategory.RATE_LIMIT),
        (client_module.VerseDBAuthError("x"), RetryCategory.AUTH),
        (client_module.VerseDBNotFoundError("x"), RetryCategory.NOT_FOUND),
        (client_module.VerseDBServerError("x"), RetryCategory.TRANSIENT),
        (client_module.VerseDBResponseError("x"), RetryCategory.INVALID),
        (httpx.UnsupportedProtocol("x"), RetryCategory.INVALID),
        (httpx.InvalidURL("x"), RetryCategory.INVALID),
        (httpx.ReadTimeout("x"), RetryCategory.TRANSIENT),
        (httpx.ConnectError("x"), RetryCategory.TRANSIENT),
        (RuntimeError("x"), None),
    ],
)
def test_classification(exc: BaseException, category: RetryCategory | None) -> None:
    assert VerseDBOnlineSource.classify_retry_exception(exc) is category


# -- cache modes ----------------------------------------------------------


def test_cache_on_answers_a_repeat_search_without_requests(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    _source(tmp_path).search(_PROFILE)
    close_shared_sessions()
    _source(tmp_path).search(_PROFILE)
    assert len(transport.requests) == 2


def test_cache_off_stores_nothing(transport: VerseDBTransport, tmp_path: Path) -> None:
    _source(tmp_path, mode=CacheMode.OFF).search(_PROFILE)
    _source(tmp_path, mode=CacheMode.OFF).search(_PROFILE)
    assert len(transport.requests) == 4
    assert not (tmp_path / "versedb_cache.sqlite").exists()


def test_cache_refresh_refetches_once_then_caches(
    transport: VerseDBTransport, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source(tmp_path).search(_PROFILE)
    close_shared_sessions()
    # A fresh process's refresh: the wipe is once per process per file.
    monkeypatch.setattr(
        "comicbox.formats.base.online.sources.base._refreshed_cache_paths", set()
    )
    _source(tmp_path, mode=CacheMode.REFRESH).search(_PROFILE)
    _source(tmp_path, mode=CacheMode.REFRESH).search(_PROFILE)
    assert len(transport.requests) == 4


# -- shared clients and lifecycle -----------------------------------------


def test_sources_with_one_token_share_one_client(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    first, second = _source(tmp_path), _source(tmp_path)
    assert first._get_client() is second._get_client()
    assert _source(tmp_path, key="other")._get_client() is not first._get_client()


def test_a_closed_client_is_rebuilt(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    source = _source(tmp_path)
    source.get(1)
    close_shared_sessions()
    assert source.get(2)["id"] == 2


def test_closing_leaves_no_resource_warning(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        source = _source(tmp_path)
        source.search(_PROFILE)
        source.get(1)
        close_shared_sessions()
        del source
        gc.collect()
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_reset_is_the_close(transport: VerseDBTransport, tmp_path: Path) -> None:
    _source(tmp_path).get(1)
    online_source.reset_shared_sessions()
    assert shared_client_rate_limit_status("token") == {}


def test_the_end_of_a_run_closes_versedb_too(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    """`run.py` releases every source's shared clients when a run ends."""
    from comicbox.run import _close_shared_online_sessions

    _source(tmp_path).get(1)
    _close_shared_online_sessions()
    assert shared_client_rate_limit_status("token") == {}


def test_the_lookup_builds_versedb_from_its_factory(tmp_path: Path) -> None:
    from comicbox.box.online_lookup import _DEFAULT_SOURCE_FACTORIES

    assert _DEFAULT_SOURCE_FACTORIES["versedb"] is VerseDBOnlineSource


# -- review fixes: cache failures, the daily cap, dual numbers -------------


def test_a_cache_that_cannot_store_does_not_resend(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    """A cache error used to escape into `with_retry`, which sent it again."""
    source = _source(tmp_path)
    cache = source._get_client()._cache
    assert cache is not None
    # Every write now fails, as on a full disk or a file another process locks.
    cache._conn.close()
    assert source.get(1)["id"] == 1
    assert len(transport.requests) == 1


def _daily_cap(monkeypatch: pytest.MonkeyPatch) -> VerseDBTransport:
    mock = VerseDBTransport(
        lambda _request: Reply(
            {"message": "Too Many Attempts."},
            status=429,
            headers={"Retry-After": "18000"},
        )
    )
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", mock.transport)

    def no_sleep(seconds: float) -> None:
        msg = f"slept {seconds}s"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "comicbox.formats.base.online.retry.interruptible_sleep", no_sleep
    )
    return mock


def test_the_daily_cap_is_never_slept_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mock = _daily_cap(monkeypatch)
    source = _source(tmp_path)
    with pytest.raises(client_module.VerseDBQuotaError):
        source.get(1)
    assert len(mock.requests) == 1


def test_the_daily_cap_skips_searches_so_other_sources_carry_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reported as skipped, not as a miss, so a later run tries the comic again."""
    from comicbox.events import SKIP_QUOTA_RESERVED

    mock = _daily_cap(monkeypatch)
    source = _source(tmp_path)
    for _ in range(3):
        assert source.search(_PROFILE) == []
        assert source.search_skip_reason == SKIP_QUOTA_RESERVED
    assert source.lookup_issue(_BLADEHAWK, "1") is None
    # One request learned the limit; nothing after it was sent.
    assert len(mock.requests) == 1


def test_a_fresh_search_clears_the_skip_reason(
    transport: VerseDBTransport, tmp_path: Path
) -> None:
    source = _source(tmp_path)
    source._note_search_skipped("x")
    source.search(_PROFILE)
    assert source.search_skip_reason is None


def test_a_dual_numbered_issue_matches_after_a_round_trip(tmp_path: Path) -> None:
    """
    "1 [10]" is written as issue 1, read back, and matches its own row again.

    Written raw it was stored as "1[10]" with a false suffix, and a later
    VerseDB search for the same comic could not match it.
    """
    from comicbox.box import Comicbox
    from comicbox.formats import MetadataFormats
    from comicbox.formats.base.online.profile import (
        accumulate_profile_fields,
        strip_issue_leading_zeros,
    )

    row = next(
        row for row in fixture("list_issues")["data"] if row["issue_number"] == "1 [10]"
    )
    issue = fixture("issue_regular")["data"]
    issue["issue_number"] = row["issue_number"]
    with Comicbox() as car:
        car.add_metadata({"versedb_api": issue}, MetadataFormats.VERSEDB_API)
        md = car.to_dict()["comicbox"]
        written = car.to_string(MetadataFormats.COMIC_INFO)
    assert (md["issue"]["name"], md["alternative_issue"]["name"]) == ("1", "10")
    with Comicbox(metadata=written, fmt=MetadataFormats.COMIC_INFO) as car:
        fields: dict[str, Any] = {}
        accumulate_profile_fields(fields, car.to_dict())
    profile = ComicProfile(**fields)
    assert online_source._number_matches(row, strip_issue_leading_zeros(profile.issue))
