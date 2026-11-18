"""
`MetronOnlineSource` cover search: Metron's ``cover_hash_near`` filter.

What the query is narrowed by, when it isn't sent at all, and the guard
against a server that ignores the filter. One test drives a real mokkari
Session over a fake transport, to pin that a 400 for a bad filter value
fails in one request instead of being retried.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger
from mokkari.exceptions import ApiError

from comicbox.config.online.settings import (
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.base.online.sources.base import OnlineSource
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.metron_api.paced_session import build_paced_session
from tests.util.metron_transport import Reply, install

if TYPE_CHECKING:
    from collections.abc import Iterator

_HASH = "95977c2b3129c2d3"


def _bits_away(bits: int) -> str:
    """Return a hash exactly ``bits`` bits from `_HASH`."""
    return f"{int(_HASH, 16) ^ ((1 << bits) - 1):016x}"


# 21 bits is one past Metron's maximum distance.
_HASH_0 = _HASH
_HASH_4 = _bits_away(4)
_HASH_20 = _bits_away(20)
_HASH_21 = _bits_away(21)
_PROFILE = ComicProfile(series="Lois Lane", issue="010", issue_int=10, year=2020)


def _row(iid: int, cover_hash: str | None, series: str = "Lois Lane") -> Any:
    """Build a `BaseIssue`-shaped row with the fields `_to_candidate` reads."""
    return SimpleNamespace(
        id=iid,
        number="10",
        cover_date=date(2020, 7, 1),
        image=f"https://example.com/{iid}.jpg",
        cover_hash=cover_hash,
        series=SimpleNamespace(id=77, name=series, volume=1, year_began=2019),
    )


class _FakeSession:
    """Records each `issues_list` call and answers with fixed rows."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def issues_list(self, params: dict | None = None) -> list[Any]:
        self.calls.append(dict(params or {}))
        return list(self.rows)


def _source(
    monkeypatch: pytest.MonkeyPatch,
    session: Any,
    *,
    series_id: int | None = None,
) -> MetronOnlineSource:
    lookup = OnlineLookupSettings(
        series_ids={"metron": series_id} if series_id is not None else {}
    )
    src = MetronOnlineSource(
        OnlineSourceCredentials(key="k"), OnlineSettings(lookup=lookup)
    )
    monkeypatch.setattr(src, "_get_session", lambda: session)
    return src


def test_query_is_narrowed_by_number_and_a_three_year_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leading zeros go, the distance is Metron's maximum, years are Y±1."""
    session = _FakeSession([_row(12547, _HASH_0)])
    src = _source(monkeypatch, session)

    assert src.can_search_by_cover(_PROFILE)
    candidates = src.search_by_cover(_PROFILE, _HASH)

    assert session.calls == [
        {
            "number": "10",
            "cover_hash_max_distance": 20,
            "cover_date_range_after": "2019-01-01",
            "cover_date_range_before": "2021-12-31",
            "cover_hash_near": _HASH,
        }
    ]
    assert [c.issue_id for c in candidates] == [12547]
    assert candidates[0].precomputed_cover_hash == _HASH_0
    assert candidates[0].volume_id == 77


def test_series_id_replaces_the_date_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """With --series-id, no year is needed and none is sent."""
    session = _FakeSession([])
    src = _source(monkeypatch, session, series_id=77)
    profile = ComicProfile(series="Lois Lane", issue="10", issue_int=10, year=None)

    assert src.can_search_by_cover(profile)
    assert src.search_by_cover(profile, _HASH) == []

    assert session.calls == [
        {
            "number": "10",
            "cover_hash_max_distance": 20,
            "series_id": 77,
            "cover_hash_near": _HASH,
        }
    ]


@pytest.mark.parametrize(
    "profile",
    [
        pytest.param(
            ComicProfile(series="Lois Lane", issue=None, year=2020), id="no-number"
        ),
        pytest.param(
            ComicProfile(series="Lois Lane", issue="", year=2020), id="blank-number"
        ),
        pytest.param(
            ComicProfile(series="Lois Lane", issue="10", issue_int=10, year=None),
            id="no-year",
        ),
        pytest.param(
            ComicProfile(series="Lois Lane", issue="10", issue_int=10, year=0),
            id="year-0000",
        ),
        pytest.param(
            ComicProfile(series="Lois Lane", issue="10", issue_int=10, year=2100),
            id="year-2100",
        ),
    ],
)
def test_too_loose_a_query_is_never_sent(
    monkeypatch: pytest.MonkeyPatch, profile: ComicProfile
) -> None:
    """Without a number, or without a year or series id, there's no request."""
    session = _FakeSession([_row(1, _HASH_0)])
    src = _source(monkeypatch, session)

    assert not src.can_search_by_cover(profile)
    assert src.search_by_cover(profile, _HASH) == []
    assert session.calls == []


def test_issue_zero_is_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """#000 is searched as Metron's "0", not mistaken for a missing number."""
    session = _FakeSession([])
    src = _source(monkeypatch, session)
    profile = ComicProfile(series="Penultiman", issue="000", issue_int=0, year=2020)

    assert src.can_search_by_cover(profile)
    src.search_by_cover(profile, _HASH)

    assert session.calls[0]["number"] == "0"


def test_quota_reserve_declines_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Like `search`, a cover search doesn't start on the day's last requests."""
    session = _FakeSession([_row(1, _HASH_0)])
    src = _source(monkeypatch, session)
    monkeypatch.setattr(src, "_may_start_cold_search", lambda: False)

    assert src.search_by_cover(_PROFILE, _HASH) == []
    assert session.calls == []


def test_rows_within_the_distance_are_kept_in_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metron's closest-first order survives; the edge of the range is kept."""
    session = _FakeSession([_row(1, _HASH_0), _row(2, _HASH_4), _row(3, _HASH_20)])
    src = _source(monkeypatch, session)

    candidates = src.search_by_cover(_PROFILE, _HASH)

    assert [c.issue_id for c in candidates] == [1, 2, 3]
    assert src.can_search_by_cover(_PROFILE)


@pytest.mark.parametrize(
    "stray",
    [
        pytest.param(_HASH_21, id="beyond-max-distance"),
        pytest.param(None, id="no-cover-hash"),
        pytest.param("not-a-hash", id="malformed-cover-hash"),
    ],
)
def test_a_server_ignoring_the_filter_turns_cover_search_off(
    monkeypatch: pytest.MonkeyPatch, stray: str | None
) -> None:
    """
    Drop rows `cover_hash_near` could not have returned, and stop searching.

    They are warned about once, and every later comic in the run is spared
    paying for the pages.
    """
    from comicbox.formats.base.online import warn_once as warn_once_module

    monkeypatch.setattr(warn_once_module, "_seen", set())
    session = _FakeSession([_row(1, _HASH_0), _row(2, stray)])
    src = _source(monkeypatch, session)

    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        candidates = src.search_by_cover(_PROFILE, _HASH)
    finally:
        logger.remove(handler_id)

    assert [c.issue_id for c in candidates] == [1]
    assert sum("cover_hash_near" in m for m in messages) == 1
    # Off for the rest of the process, for every source instance.
    later = _source(monkeypatch, _FakeSession([]))
    assert not later.can_search_by_cover(_PROFILE)


def test_sources_without_a_cover_search_decline() -> None:
    """The base class says no, so the box never reads the cover for them."""
    src = MetronOnlineSource(OnlineSourceCredentials(key="k"), OnlineSettings())
    assert OnlineSource.can_search_by_cover(src, _PROFILE) is False
    with pytest.raises(NotImplementedError):
        OnlineSource.search_by_cover(src, _PROFILE, _HASH)


@pytest.fixture
def real_session() -> Iterator[Any]:
    """Yield a paced mokkari Session with no response cache."""
    session = build_paced_session(
        RateGate(default_limit=1000), api_token="t", cache=None
    )
    yield session
    session.close()


def test_a_rejected_filter_value_fails_in_one_request(
    monkeypatch: pytest.MonkeyPatch, real_session: Any
) -> None:
    """A 400 is a request comicbox built wrong: no retries, no sleeps."""
    src = _source(monkeypatch, real_session)
    sleeps: list[float] = []
    src.retry_sleep = sleeps.append
    adapter = install(
        real_session,
        [
            Reply(
                {
                    "cover_hash_near": [
                        "Enter a 16-character hexadecimal perceptual hash."
                    ]
                },
                status_code=400,
            )
        ],
    )

    with pytest.raises(ApiError):
        src.search_by_cover(_PROFILE, _HASH)

    assert len(adapter.urls) == 1
    assert f"cover_hash_near={_HASH}" in adapter.urls[0]
    assert "cover_hash_max_distance=20" in adapter.urls[0]
    assert sleeps == []
