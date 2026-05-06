"""Programmatic SelectorCallback tests for the M5 prompt path."""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup, OnlineLookupAbortedError
from comicbox.formats import MetadataFormats
from comicbox.online.profile import Candidate, CandidateSummary
from comicbox.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.online.selector import SelectorContext


def _candidate_payload(issue_id: int) -> dict:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "Pub"},
        "series": {"id": 1, "name": "S", "year_began": 2020, "volume": 1},
    }


class _AmbiguousMetron:
    """Mock source that returns two ambiguous candidates."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings) -> None:
        self._credentials = credentials
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return bool(self._credentials.username and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return _candidate_payload(issue_id)

    def search(self, profile) -> list[Candidate]:
        # Return two close-scoring candidates so resolution is PROMPT under
        # the default policy.
        def _make(issue_id: int, year: int) -> Candidate:
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
        # Year off-by-one differentiates them slightly but both clear min_confidence.
        return [_make(101, 2020), _make(102, 2021)]


@pytest.fixture
def patched_metron(monkeypatch: pytest.MonkeyPatch) -> list[_AmbiguousMetron]:
    instances: list[_AmbiguousMetron] = []

    def factory(creds, settings):
        src = _AmbiguousMetron(creds, settings)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _build_cb(profile_metadata: dict | None = None) -> Comicbox:
    """Comicbox with metron-search trigger and provided profile metadata."""
    cli_md = profile_metadata or {
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
            metadata=cli_md,
            online={"metron": {"username": "u", "password": "p"}},
        )
    )
    return Comicbox(config=args)


def test_choose_index_writes_candidate(patched_metron) -> None:
    selections: list[SelectorContext] = []

    def selector(profile, candidates, ctx):
        selections.append(ctx)
        return ("choose", 0)

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.run_online_lookup()
    assert len(selections) == 1
    assert selections[0].source == "metron"
    # Candidate 0 has issue_id=101.
    assert patched_metron[0].get_calls == [101]


def test_skip_drops_file(patched_metron) -> None:
    def selector(profile, candidates, ctx):
        return ("skip", None)

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.run_online_lookup()
    assert patched_metron[0].get_calls == []


def test_abort_raises(patched_metron) -> None:
    def selector(profile, candidates, ctx):
        return ("abort", None)

    cb = _build_cb()
    cb.set_online_selector(selector)
    with pytest.raises(OnlineLookupAbortedError):
        cb.run_online_lookup()


def test_manual_id_fetches_routed_source(patched_metron) -> None:
    def selector(profile, candidates, ctx):
        return ("manual", "metron:999")

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.run_online_lookup()
    assert patched_metron[0].get_calls == [999]


def test_manual_id_for_other_source_skipped(patched_metron) -> None:
    def selector(profile, candidates, ctx):
        return ("manual", "comicvine:42")

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.run_online_lookup()
    # Mismatched source — not fetched.
    assert patched_metron[0].get_calls == []


def test_selector_receives_candidates(patched_metron) -> None:
    captured: dict = {}

    def selector(profile, candidates, ctx):
        captured["profile"] = profile
        captured["candidates"] = list(candidates)
        return ("skip", None)

    cb = _build_cb()
    cb.set_online_selector(selector)
    cb.run_online_lookup()
    assert captured["profile"].series == "Foo Comics"
    assert len(captured["candidates"]) == 2
    assert captured["candidates"][0].issue_id in {101, 102}
