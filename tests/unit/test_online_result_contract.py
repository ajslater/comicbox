"""
Online-lookup result-contract tests.

Three defects lived in the gap between "we decided to accept a candidate"
and "the follow-up fetch actually landed":

1. The pinned-id fast paths (``--id`` and the stored-id refresh) returned
   an unconditional win, so a failed fetch reported ``written`` with
   nothing written.
2. ``record_auto_write`` and the ``AutoWritten`` event fired before the
   fetch, so the summary and the event stream counted wins that never
   happened.
3. The prompt loop was unbounded and indexed the candidate list with an
   unchecked selector-supplied integer.
"""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import (
    _MAX_PROMPT_ROUNDS,
    ComicboxOnlineLookup,
    _series_fingerprint,
)
from comicbox.events import AutoWritten, Event, FileFinished
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.formats.base.online.selector import SelectorContext


class _FetchFailedError(Exception):
    """Stand-in for any source-side failure of the issue fetch."""


def setup_function() -> None:
    outcome_stats.reset()


def _payload(issue_id: int) -> dict:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "Quality Comics"},
        "series": {"id": 1, "name": "Foo Comics", "year_began": 2020, "volume": 1},
    }


def _candidate(issue_id: int, *, volume_id: int | None = None) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series="Foo Comics",
            issue="5",
            year=2020,
            publisher="Quality Comics",
            page_count=24,
            cover_url=None,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


class _FakeMetron:
    """Metron stand-in whose ``get()`` can be made to fail."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings, *, candidates=(), fail_get=False) -> None:
        self._credentials = credentials
        self._candidates = list(candidates)
        self._fail_get = fail_get
        self.get_calls: list[int] = []
        self.search_calls = 0
        self.lookup_calls: list[tuple[int, str | None]] = []

    def is_configured(self) -> bool:
        return bool(self._credentials.user and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        if self._fail_get:
            msg = f"metron is down (issue {issue_id})"
            raise _FetchFailedError(msg)
        return _payload(issue_id)

    def search(self, profile) -> list[Candidate]:
        self.search_calls += 1
        return list(self._candidates)

    def lookup_issue(self, volume_id: int, issue_number: str | None):
        self.lookup_calls.append((volume_id, issue_number))
        for cand in self._candidates:
            if cand.volume_id == volume_id:
                return cand
        return None


class _FakeCV:
    """Comic Vine stand-in; records whether first-wins let it run."""

    name = "comicvine"
    metadata_source = MetadataSources.COMICVINE_API
    metadata_format = MetadataFormats.COMICVINE_API

    def __init__(self, credentials, settings) -> None:
        self._credentials = credentials
        self.get_calls: list[int] = []
        self.search_calls = 0

    def is_configured(self) -> bool:
        return bool(self._credentials.key)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return {"results": _payload(issue_id)}

    def search(self, profile) -> list[Candidate]:
        self.search_calls += 1
        return [_candidate(999)]


def _patch_metron(monkeypatch, **kwargs) -> list[_FakeMetron]:
    instances: list[_FakeMetron] = []

    def factory(creds, settings):
        src = _FakeMetron(creds, settings, **kwargs)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _patch_both(monkeypatch, **kwargs) -> tuple[list[_FakeMetron], list[_FakeCV]]:
    metrons: list[_FakeMetron] = []
    cvs: list[_FakeCV] = []

    def metron_factory(creds, settings):
        src = _FakeMetron(creds, settings, **kwargs)
        metrons.append(src)
        return src

    def cv_factory(creds, settings):
        src = _FakeCV(creds, settings)
        cvs.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": metron_factory, "comicvine": cv_factory}),
    )
    return metrons, cvs


_PROFILE_MD = {
    "comicbox": {
        "series": {"name": "Foo Comics"},
        "issue": {"name": "5"},
        "date": {"year": 2020},
        "publisher": {"name": "Quality Comics"},
        "page_count": 24,
    }
}


def _build_cb(**overrides: Any) -> Comicbox:
    kwargs: dict[str, Any] = {
        "online_sources": ["metron"],
        "general": Namespace(metadata=_PROFILE_MD),
        "auth": ["metron:user=u", "metron:pass=p"],
    }
    kwargs.update(overrides)
    return Comicbox(config=Namespace(comicbox=Namespace(**kwargs)))


def _run(cb: Comicbox) -> tuple[bool, list[Event]]:
    events: list[Event] = []
    cb.set_event_handler(events.append)
    return cb.run_online_lookup(), events


def _outcome(events: list[Event]) -> str | None:
    for event in events:
        if isinstance(event, FileFinished):
            return event.outcome
    return None


# --- 1. a failed pinned fetch is not a win ----------------------------------


def test_failed_explicit_id_fetch_reports_no_change(monkeypatch) -> None:
    """--id whose fetch raises must not report ``written``."""
    instances = _patch_metron(monkeypatch, fail_get=True)
    cb = _build_cb(explicit_ids=["metron:42"])

    applied, events = _run(cb)

    assert instances[0].get_calls == [42]
    assert applied is False
    assert _outcome(events) == "no_change"
    assert not [e for e in events if isinstance(e, AutoWritten)]
    # Nothing landed, so nothing is counted -- not even as an id-fetch.
    assert outcome_stats.has_any_activity() is False


def test_successful_explicit_id_fetch_still_reports_written(monkeypatch) -> None:
    """The success path is unchanged: applied, announced, counted."""
    instances = _patch_metron(monkeypatch)
    cb = _build_cb(explicit_ids=["metron:42"])

    applied, events = _run(cb)

    assert instances[0].get_calls == [42]
    assert applied is True
    assert _outcome(events) == "written"
    assert [e.candidate_summary for e in events if isinstance(e, AutoWritten)] == ["42"]
    assert "1 fetched by --id" in "\n".join(outcome_stats.summary_lines())


def test_failed_explicit_id_fetch_still_claims_the_comic(monkeypatch) -> None:
    """
    A pinned id the user gave us suppresses the sibling source either way.

    ``applied`` and ``claimed`` are separate signals: the run honestly
    reports that nothing was written, but Comic Vine is still kept from
    fuzzy-matching a comic whose exact issue the user already named.
    """
    metrons, cvs = _patch_both(monkeypatch, fail_get=True)
    cb = _build_cb(
        online_sources=["metron", "comicvine"],
        explicit_ids=["metron:42"],
        auth=["metron:user=u", "metron:pass=p", "comicvine:key=k"],
    )

    applied, events = _run(cb)

    assert metrons[0].get_calls == [42]
    assert applied is False
    assert _outcome(events) == "no_change"
    # Claimed: CV never searched behind the failed pin.
    assert cvs[0].search_calls == 0
    assert cvs[0].get_calls == []


def test_failed_stored_id_refresh_reports_no_change(monkeypatch) -> None:
    """The stored-id fast path has the same contract as --id."""
    instances = _patch_metron(monkeypatch, fail_get=True)
    md = {
        "comicbox": {
            **_PROFILE_MD["comicbox"],
            "identifiers": {"metron": {"key": "77"}},
        }
    }
    cb = _build_cb(general=Namespace(metadata=md))

    applied, events = _run(cb)

    assert instances[0].get_calls == [77]
    assert instances[0].search_calls == 0
    assert applied is False
    assert _outcome(events) == "no_change"
    assert not [e for e in events if isinstance(e, AutoWritten)]


def test_successful_stored_id_refresh_reports_written(monkeypatch) -> None:
    """A landed stored-id refresh is an auto-write, counted as one."""
    instances = _patch_metron(monkeypatch)
    md = {
        "comicbox": {
            **_PROFILE_MD["comicbox"],
            "identifiers": {"metron": {"key": "77"}},
        }
    }
    cb = _build_cb(general=Namespace(metadata=md))

    applied, events = _run(cb)

    assert instances[0].get_calls == [77]
    assert applied is True
    assert _outcome(events) == "written"
    assert [e.candidate_summary for e in events if isinstance(e, AutoWritten)] == ["77"]


# --- 2. outcome recording happens only after the fetch lands ----------------


def test_failed_auto_write_fetch_records_nothing(monkeypatch) -> None:
    """A cold-path AUTO_WRITE whose fetch fails is not counted or announced."""
    instances = _patch_metron(monkeypatch, candidates=[_candidate(101)], fail_get=True)
    cb = _build_cb()

    applied, events = _run(cb)

    assert instances[0].search_calls == 1
    assert instances[0].get_calls == [101]
    assert applied is False
    assert _outcome(events) == "no_change"
    assert not [e for e in events if isinstance(e, AutoWritten)]
    assert outcome_stats.has_any_activity() is False


def test_failed_series_cache_accept_records_nothing(monkeypatch) -> None:
    """The warm series-cache path funnels through the same chokepoint."""
    instances = _patch_metron(
        monkeypatch, candidates=[_candidate(101, volume_id=42)], fail_get=True
    )
    fingerprint = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    cb = _build_cb()
    cb.set_series_cache({("metron", fingerprint): 42})

    applied, events = _run(cb)

    assert instances[0].lookup_calls == [(42, "5")]
    # A source-side failure on the warm path degrades to the cold-path
    # search (documented in _try_series_cache_lookup), which re-picks the
    # same issue and fails the same way. Neither attempt may be counted.
    assert instances[0].get_calls == [101, 101]
    assert applied is False
    assert not [e for e in events if isinstance(e, AutoWritten)]
    assert outcome_stats.has_any_activity() is False


def test_failed_prompt_choice_fetch_is_not_counted_as_accepted(monkeypatch) -> None:
    """A prompt-chosen candidate whose fetch fails isn't a prompt-accepted win."""
    instances = _patch_metron(
        monkeypatch,
        candidates=[_candidate(101), _candidate(102)],
        fail_get=True,
    )

    def selector(profile, candidates, ctx):
        return ("choose", 0)

    cb = _build_cb()
    cb.set_online_selector(selector)

    applied, _events = _run(cb)

    assert instances[0].get_calls == [101]
    assert applied is False
    assert outcome_stats.has_any_activity() is False


# --- 3. the prompt loop is bounded, and its index is checked ----------------


@pytest.mark.parametrize("index", [2, 7, -1, -5])
def test_prompt_choose_out_of_range_index_is_declined(monkeypatch, index) -> None:
    """
    An out-of-range selector index skips instead of tagging.

    Negative indices are the dangerous half: Python reads them as valid
    from-the-end lookups, so an unchecked -1 silently tags the comic with
    the last candidate nobody chose.
    """
    instances = _patch_metron(
        monkeypatch, candidates=[_candidate(101), _candidate(102)]
    )

    def selector(profile, candidates, ctx):
        return ("choose", index)

    cb = _build_cb()
    cb.set_online_selector(selector)

    applied, _events = _run(cb)

    assert instances[0].get_calls == []
    assert applied is False
    assert "declined 1" in "\n".join(outcome_stats.summary_lines())


def test_prompt_choose_in_range_index_still_works(monkeypatch) -> None:
    """The bounds check doesn't get in the way of a legitimate choice."""
    instances = _patch_metron(
        monkeypatch, candidates=[_candidate(101), _candidate(102)]
    )

    def selector(profile, candidates, ctx):
        return ("choose", 1)

    cb = _build_cb()
    cb.set_online_selector(selector)

    applied, _events = _run(cb)

    assert instances[0].get_calls == [102]
    assert applied is True


def test_prompt_loop_caps_repeated_session_changes(monkeypatch) -> None:
    """
    A selector that only ever asks for session changes must terminate.

    ``set_policy`` / ``set_unattended`` re-resolve and re-prompt, so a
    callback that never returns a terminal action span the loop forever.
    """
    instances = _patch_metron(
        monkeypatch, candidates=[_candidate(101), _candidate(102)]
    )
    calls: list[SelectorContext] = []

    def selector(profile, candidates, ctx):
        calls.append(ctx)
        return ("set_policy", "ask")

    cb = _build_cb()
    cb.set_online_selector(selector)

    applied, _events = _run(cb)

    assert len(calls) == _MAX_PROMPT_ROUNDS
    assert applied is False
    assert instances[0].get_calls == []
    assert "declined 1" in "\n".join(outcome_stats.summary_lines())
