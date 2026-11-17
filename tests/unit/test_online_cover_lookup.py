"""
The lookup's cover step: a source that can search by cover is asked first.

A match the cover verdict accepts is written without the name search; any
other outcome falls through to the name search unchanged. Drives the real
`Comicbox` lookup with a fake source and the comic's cover hashes stubbed.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.events import AutoWritten, Event, SearchCompleted, SearchStarted
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.cover_hash import (
    FULL_COVER_ACCEPT_BITS,
    HALF_COVER_ACCEPT_BITS,
    CoverPart,
    SearchHash,
)
from comicbox.formats.base.online.profile import Candidate, CandidateSummary
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from collections.abc import Sequence

_HASH = "95977c2b3129c2d3"
_FULL = (SearchHash(_HASH, FULL_COVER_ACCEPT_BITS, CoverPart.FULL),)


def _bits_away(bits: int, base: str = _HASH) -> str:
    """Return a hash exactly ``bits`` bits from ``base``."""
    return f"{int(base, 16) ^ ((1 << bits) - 1):016x}"


def _candidate(
    iid: int, bits: int, series: str = "Lois Lane", volume_id: int = 77
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=iid,
        summary=CandidateSummary(
            series=series,
            issue="5",
            year=2020,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
        ),
        precomputed_cover_hash=_bits_away(bits),
        volume_id=volume_id,
    )


def _payload(issue_id: int) -> dict[str, Any]:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "DC Comics"},
        "series": {"id": 77, "name": "Lois Lane", "year_began": 2019, "volume": 1},
    }


class _CoverSource:
    """A source with a cover search; records what the lookup asked of it."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(
        self,
        credentials: Any,
        settings: Any,
        cover_replies: list[list[Candidate] | Exception],
        name_candidates: Sequence[Candidate],
        get_error: Exception | None,
    ) -> None:
        del credentials, settings
        self._cover_replies = cover_replies
        self._name_candidates = list(name_candidates)
        self._get_error = get_error
        self.cover_calls: list[str] = []
        self.search_calls = 0
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return True

    def can_search_by_cover(self, profile: Any) -> bool:
        del profile
        return True

    def search_by_cover(self, profile: Any, cover_hash: str) -> list[Candidate]:
        del profile
        self.cover_calls.append(cover_hash)
        reply = self._cover_replies.pop(0) if self._cover_replies else []
        if isinstance(reply, Exception):
            raise reply
        return reply

    def search(self, profile: Any) -> list[Candidate]:
        del profile
        self.search_calls += 1
        return list(self._name_candidates)

    def get(self, issue_id: int) -> dict[str, Any]:
        self.get_calls.append(issue_id)
        if self._get_error is not None:
            error, self._get_error = self._get_error, None
            raise error
        return _payload(issue_id)

    def prefetch_volume(self, volume_id: int, cluster_size: int) -> None:
        del volume_id, cluster_size


class _Run:
    """One lookup: the box, its fake source, events and series cache."""

    def __init__(self, source: _CoverSource, events: list[Event], cache: dict) -> None:
        self.source = source
        self.events = events
        self.cache = cache

    def kinds(self, kind: type[Event]) -> list[Event]:
        return [e for e in self.events if isinstance(e, kind)]


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cover_replies: list[list[Candidate] | Exception],
    name_candidates: Sequence[Candidate] = (),
    hashes: tuple[SearchHash, ...] = _FULL,
    series: str = "Lois Lane",
    get_error: Exception | None = None,
    **comicbox_options: Any,
) -> _Run:
    sources: list[_CoverSource] = []

    def factory(creds: Any, settings: Any) -> _CoverSource:
        src = _CoverSource(creds, settings, cover_replies, name_candidates, get_error)
        sources.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    metadata = {
        "comicbox": {
            "series": {"name": series},
            "issue": {"name": "5"},
            "date": {"year": 2020},
        }
    }
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata=metadata),
            auth=["metron:key=k"],
            prompts="never",
            **comicbox_options,
        )
    )
    cb = Comicbox(config=args)
    monkeypatch.setattr(cb, "_local_cover_search_hashes", lambda: hashes)
    events: list[Event] = []
    cache: dict = {}
    cb.set_event_handler(events.append)
    cb.set_series_cache(cache)
    cb.run_online_lookup()
    return _Run(sources[0], events, cache)


def test_an_accepted_cover_match_skips_the_name_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(monkeypatch, cover_replies=[[_candidate(9110, 4), _candidate(1, 20)]])

    assert run.source.cover_calls == [_HASH]
    assert run.source.search_calls == 0
    assert run.source.get_calls == [9110]
    assert len(run.kinds(SearchStarted)) == 1
    (completed,) = run.kinds(SearchCompleted)
    assert isinstance(completed, SearchCompleted)
    assert completed.n_candidates == 2
    (written,) = run.kinds(AutoWritten)
    assert isinstance(written, AutoWritten)
    assert written.candidate_summary == "9110"


def test_an_unaccepted_cover_falls_through_to_the_name_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tie is never taken; the name search decides, as it did before."""
    run = _run(
        monkeypatch,
        cover_replies=[[_candidate(1, 3), _candidate(2, 3)]],
        name_candidates=[_candidate(3, 30)],
    )

    assert run.source.cover_calls == [_HASH]
    assert run.source.search_calls == 1
    # One search, as far as an event consumer can tell.
    assert len(run.kinds(SearchStarted)) == 1
    assert len(run.kinds(SearchCompleted)) == 1


def test_ask_mode_never_sends_a_cover_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ask`` never writes unprompted, so the request would be wasted."""
    run = _run(monkeypatch, cover_replies=[[_candidate(9110, 0)]], match="ask")

    assert run.source.cover_calls == []
    assert run.source.search_calls == 1
    assert run.source.get_calls == []


def test_careful_mode_writes_a_cover_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """AJ's decision: the calibrated cover rule writes under careful too."""
    run = _run(monkeypatch, cover_replies=[[_candidate(9110, 4)]], match="careful")

    assert run.source.get_calls == [9110]
    assert run.source.search_calls == 0


def test_a_spread_tries_its_halves_in_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """The right half's results don't decide, so the left half is searched."""
    right, left = _bits_away(30), _bits_away(40)
    hashes = (
        SearchHash(right, HALF_COVER_ACCEPT_BITS, CoverPart.RIGHT),
        SearchHash(left, HALF_COVER_ACCEPT_BITS, CoverPart.LEFT),
        SearchHash(_HASH, FULL_COVER_ACCEPT_BITS, CoverPart.FULL),
    )
    # Right half: the closest row is 15 bits off, past its 10-bit limit.
    off_right = replace(_candidate(4, 0), precomputed_cover_hash=_bits_away(15, right))
    on_left = replace(_candidate(5, 0), precomputed_cover_hash=left)
    run = _run(monkeypatch, hashes=hashes, cover_replies=[[off_right], [on_left]])

    assert run.source.cover_calls == [right, left]
    assert run.source.get_calls == [5]
    assert run.source.search_calls == 0


def test_a_series_mismatch_is_left_to_the_name_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(
        monkeypatch,
        cover_replies=[[_candidate(1, 2, series="Monster High")]],
        name_candidates=[_candidate(3, 30)],
    )

    # The name search's own match is written, not the other series' cover.
    assert run.source.get_calls == [3]
    assert run.source.search_calls == 1


def test_a_pinned_series_takes_any_series_name(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(
        monkeypatch,
        cover_replies=[[_candidate(1, 2, series="Superman's Girl Friend")]],
        explicit_series_ids=["metron:77"],
    )

    assert run.source.get_calls == [1]
    assert run.source.search_calls == 0


def test_a_failed_cover_search_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(monkeypatch, cover_replies=[RuntimeError("502")])

    assert run.source.cover_calls == [_HASH]
    assert run.source.search_calls == 1


def test_an_abort_during_the_cover_search_ends_the_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(OnlineLookupAbortedError):
        _run(monkeypatch, cover_replies=[OnlineLookupAbortedError("cancelled")])


def test_a_failed_fetch_of_a_cover_match_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As after a series-cache hit whose fetch fails: the name search runs."""
    run = _run(
        monkeypatch,
        cover_replies=[[_candidate(9110, 4)]],
        get_error=RuntimeError("fetch failed"),
    )

    assert run.source.get_calls[0] == 9110
    assert run.source.search_calls == 1


@pytest.mark.parametrize(
    ("profile_series", "metron_series", "cached"),
    [
        pytest.param("Lois Lane", "Lois Lane", True, id="same-name-is-cached"),
        pytest.param(
            "Amazing Spider-Man",
            "The Amazing Spider-Man",
            True,
            id="article-differs-is-cached",
        ),
        # The next "Star Wars #5" from any Star Wars series would otherwise
        # be tagged as Boba Fett #5 without a search.
        pytest.param(
            "Star Wars",
            "Star Wars: The Book of Boba Fett",
            False,
            id="part-of-the-name-is-not-cached",
        ),
    ],
)
def test_only_a_cover_match_on_the_same_name_seeds_the_series_cache(
    monkeypatch: pytest.MonkeyPatch,
    profile_series: str,
    metron_series: str,
    *,
    cached: bool,
) -> None:
    run = _run(
        monkeypatch,
        series=profile_series,
        cover_replies=[[_candidate(9110, 4, series=metron_series, volume_id=77)]],
    )

    assert run.source.get_calls == [9110]
    assert (77 in run.cache.values()) is cached
