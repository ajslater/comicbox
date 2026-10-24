"""
Metron's prompt-time series lookup, `enrich_prompt_candidates`.

Metron's issue rows carry no publication format, publisher or series
issue count, so two issues of same-named series ("Batman #1 (2016)")
read identically in a prompt. A `series(id)` request tells them apart,
but costs a request per series, so it is paid only for candidates that
would otherwise read identically and only while the daily quota allows
discretionary work.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.profile import Candidate, CandidateSummary
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.formats.metron_api.online_source import (
    _MAX_PROMPT_SERIES_LOOKUPS,
    MetronOnlineSource,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _cand(
    issue_id: int,
    volume_id: int | None,
    *,
    series: str = "Batman",
    issue: str = "1",
    series_start_year: int | None = 2016,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series=series,
            issue=issue,
            year=2016,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
            volume=3,
            series_start_year=series_start_year,
        ),
        score=0.9,
        metadata_score=0.95,
        volume_id=volume_id,
    )


def _series(series_type: str, publisher: str, issue_count: int) -> Any:
    """Stand-in for mokkari's `Series`: `GenericItem`s carry `.name`."""
    return SimpleNamespace(
        series_type=SimpleNamespace(name=series_type),
        publisher=SimpleNamespace(name=publisher),
        issue_count=issue_count,
    )


class _FakeSession:
    """Records `series(id)` calls; an exception in ``by_id`` is raised."""

    def __init__(self, by_id: Mapping[int, Any]) -> None:
        self._by_id = by_id
        self.series_calls: list[int] = []

    def series(self, series_id: int) -> Any:
        self.series_calls.append(series_id)
        result = self._by_id.get(series_id)
        if isinstance(result, BaseException):
            raise result
        return result


class _FakeGate:
    def __init__(self, *, allow: bool) -> None:
        self._allow = allow

    def allow_cold_search(self) -> bool:
        return self._allow


def _source(
    monkeypatch: pytest.MonkeyPatch,
    session: _FakeSession,
    *,
    allow: bool = True,
) -> MetronOnlineSource:
    src = MetronOnlineSource(OnlineSourceCredentials(key="k"), OnlineSettings())
    monkeypatch.setattr(src, "_get_session", lambda: session)
    monkeypatch.setattr(src, "_gate", lambda: _FakeGate(allow=allow))
    src.retry_sleep = lambda _seconds: None
    return src


_ONGOING = _series("Ongoing Series", "DC Comics", 85)
_TPB = _series("Trade Paperback", "DC Comics", 1)


def test_identical_titles_in_different_series_get_series_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one case worth a request: same title, different series."""
    session = _FakeSession({100: _ONGOING, 200: _TPB})
    src = _source(monkeypatch, session)
    other = _cand(3, 300, issue="2")
    candidates = (_cand(1, 100), _cand(2, 200), other)

    enriched = src.enrich_prompt_candidates(candidates)

    assert session.series_calls == [100, 200]
    first, second, third = enriched
    assert first.summary.series_type == "Ongoing Series"
    assert first.summary.series_publisher == "DC Comics"
    assert first.summary.series_issue_count == 85
    assert second.summary.series_type == "Trade Paperback"
    # A candidate that already reads differently is left alone.
    assert third is other


def test_enrichment_keeps_order_length_and_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selector's `choose` index points into the box's own tuple."""
    session = _FakeSession({100: _ONGOING, 200: _TPB})
    src = _source(monkeypatch, session)
    candidates = (_cand(1, 100), _cand(3, 300, issue="2"), _cand(2, 200))

    enriched = src.enrich_prompt_candidates(candidates)

    assert [c.issue_id for c in enriched] == [1, 3, 2]
    assert [c.volume_id for c in enriched] == [100, 300, 200]
    assert [c.score for c in enriched] == [c.score for c in candidates]
    assert [c.metadata_score for c in enriched] == [
        c.metadata_score for c in candidates
    ]


@pytest.mark.parametrize(
    "candidates",
    [
        # Different series start years already tell them apart.
        (_cand(1, 100, series_start_year=2011), _cand(2, 200)),
        # Different issue numbers read differently.
        (_cand(1, 100), _cand(2, 200, issue="2")),
        # One series: its format could not tell its issues apart.
        (_cand(1, 100), _cand(2, 100)),
        # A lone candidate collides with nothing.
        (_cand(1, 100),),
    ],
    ids=["start-year", "issue", "same-series", "single"],
)
def test_no_request_without_a_collision(
    monkeypatch: pytest.MonkeyPatch, candidates: tuple[Candidate, ...]
) -> None:
    session = _FakeSession({100: _ONGOING, 200: _TPB})
    src = _source(monkeypatch, session)

    enriched = src.enrich_prompt_candidates(candidates)

    assert session.series_calls == []
    assert enriched == candidates


def test_series_names_collide_regardless_of_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession({100: _ONGOING, 200: _TPB})
    src = _source(monkeypatch, session)

    src.enrich_prompt_candidates((_cand(1, 100), _cand(2, 200, series="BATMAN")))

    assert session.series_calls == [100, 200]


def test_lookups_are_capped_per_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pathological collision cannot spend the quota."""
    ids = range(100, 100 + _MAX_PROMPT_SERIES_LOOKUPS + 2)
    session = _FakeSession(dict.fromkeys(ids, _ONGOING))
    src = _source(monkeypatch, session)

    src.enrich_prompt_candidates(tuple(_cand(vid, vid) for vid in ids))

    assert session.series_calls == list(ids)[:_MAX_PROMPT_SERIES_LOOKUPS]


def test_no_request_once_the_quota_reserve_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Display detail is discretionary; the reserve finishes matched comics."""
    session = _FakeSession({100: _ONGOING, 200: _TPB})
    src = _source(monkeypatch, session, allow=False)
    candidates = (_cand(1, 100), _cand(2, 200))

    assert src.enrich_prompt_candidates(candidates) == candidates
    assert session.series_calls == []


def test_a_failed_lookup_loses_only_that_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession({100: ValueError("boom"), 200: _TPB})
    src = _source(monkeypatch, session)
    candidates = (_cand(1, 100), _cand(2, 200))

    first, second = src.enrich_prompt_candidates(candidates)

    assert first is candidates[0]
    assert second.summary.series_type == "Trade Paperback"


def test_an_abort_ends_the_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation is not a failure to degrade past."""
    session = _FakeSession({100: OnlineLookupAbortedError("cancelled")})
    src = _source(monkeypatch, session)

    with pytest.raises(OnlineLookupAbortedError):
        src.enrich_prompt_candidates((_cand(1, 100), _cand(2, 200)))


def test_comicvine_leaves_candidates_unchanged() -> None:
    """The base hook is a no-op: Comic Vine's rows are already complete."""
    src = ComicVineOnlineSource(OnlineSourceCredentials(key="k"), OnlineSettings())
    candidates = (_cand(1, 100), _cand(2, 200))

    assert src.enrich_prompt_candidates(candidates) == candidates
