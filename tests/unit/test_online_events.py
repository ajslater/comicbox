"""End-to-end tests for online-lookup event emission."""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TypeVar

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.events import (
    AutoWritten,
    Event,
    FileFinished,
    PromptQueued,
    PromptResolved,
    SearchCompleted,
    SearchStarted,
    Skipped,
)
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import Candidate, CandidateSummary
from comicbox.formats.sources import MetadataSources

# --- mock source ------------------------------------------------------------


def _candidate_payload(issue_id: int) -> dict:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "Pub"},
        "series": {"id": 1, "name": "S", "year_began": 2020, "volume": 1},
    }


class _MockMetron:
    """Mock metron that returns candidates and records get() calls."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings, candidates) -> None:
        self._credentials = credentials
        self._candidates = candidates
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return bool(self._credentials.user and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return _candidate_payload(issue_id)

    def search(self, profile) -> list[Candidate]:
        return list(self._candidates)


def _make_candidate(issue_id: int, year: int) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series="Foo Comics",
            issue="5",
            year=year,
            publisher="Quality Comics",
            page_count=24,
            cover_url=None,
            variant_label=None,
        ),
    )


def _patch_metron(monkeypatch, candidates):
    instances: list[_MockMetron] = []

    def factory(creds, settings):
        src = _MockMetron(creds, settings, candidates)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _build_cb() -> Comicbox:
    cli_md = {
        "comicbox": {
            "series": {"name": "Foo Comics"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
            "publisher": {"name": "Quality Comics"},
            "page_count": 24,
        }
    }
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata=cli_md),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    return Comicbox(config=args)


# --- tests ------------------------------------------------------------------


_E = TypeVar("_E", bound=Event)


def _first(events: list[Event], cls: type[_E]) -> _E:
    """Return the first event of the given type; raises StopIteration if absent."""
    return next(e for e in events if isinstance(e, cls))


def test_unambiguous_candidate_emits_search_and_auto_written(monkeypatch) -> None:
    """A single high-confidence candidate triggers SearchStarted→Completed→AutoWritten→FileFinished."""
    _patch_metron(monkeypatch, [_make_candidate(101, 2020)])
    events: list[Event] = []
    cb = _build_cb()
    cb.set_event_handler(events.append)
    cb.run_online_lookup()

    kinds = {type(e).__name__ for e in events}
    expected_kinds = {"SearchStarted", "SearchCompleted", "AutoWritten", "FileFinished"}
    assert expected_kinds <= kinds

    auto = _first(events, AutoWritten)
    assert (auto.source, auto.candidate_summary) == ("metron", "101")

    completed = _first(events, SearchCompleted)
    assert (completed.n_candidates, completed.source) == (1, "metron")

    finished = _first(events, FileFinished)
    assert finished.outcome == "written"


def test_ambiguous_emits_prompt_queued_and_resolved(monkeypatch) -> None:
    """Two close-scoring candidates trigger PromptQueued + PromptResolved."""
    candidates = [_make_candidate(101, 2020), _make_candidate(102, 2021)]
    _patch_metron(monkeypatch, candidates)
    events: list[Event] = []

    def selector(profile, cands, ctx):
        return ("choose", 0)

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.set_event_handler(events.append)
    cb.run_online_lookup()

    queued = [e for e in events if isinstance(e, PromptQueued)]
    resolved = [e for e in events if isinstance(e, PromptResolved)]
    assert len(queued) == 1
    assert len(resolved) == 1
    assert resolved[0].action == "choose"
    assert queued[0].n_candidates == 2


def test_no_search_criteria_skips_silently(monkeypatch) -> None:
    """Missing search profile fields → no SearchStarted, but FileFinished still fires."""
    _patch_metron(monkeypatch, [])
    events: list[Event] = []
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata={"comicbox": {}}),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    with Comicbox(config=args) as cb:
        cb.set_event_handler(events.append)
        cb.run_online_lookup()

    assert not [e for e in events if isinstance(e, SearchStarted)]
    finished = [e for e in events if isinstance(e, FileFinished)]
    assert finished
    assert finished[-1].outcome == "no_change"


def test_event_handler_absent_is_a_noop(monkeypatch) -> None:
    """Without a handler the lookup still works; no exceptions, no recorded events."""
    _patch_metron(monkeypatch, [_make_candidate(101, 2020)])
    cb = _build_cb()
    # No set_event_handler — run should succeed silently.
    cb.run_online_lookup()


def test_no_match_emits_no_match_event(monkeypatch) -> None:
    """Empty candidate list ⇒ no SearchCompleted top score, no NoMatch (matcher unreached)."""
    _patch_metron(monkeypatch, [])
    events: list[Event] = []
    cb = _build_cb()
    cb.set_event_handler(events.append)
    cb.run_online_lookup()

    # SearchCompleted should fire with n_candidates=0
    completed = [e for e in events if isinstance(e, SearchCompleted)]
    assert len(completed) == 1
    assert completed[0].n_candidates == 0
    assert completed[0].top_score is None
    # No AutoWritten / Skipped / PromptQueued for the empty case
    assert not any(isinstance(e, AutoWritten | Skipped | PromptQueued) for e in events)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
