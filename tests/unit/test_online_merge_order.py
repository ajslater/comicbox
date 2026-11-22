"""
Online sources merge in run order: the first-listed source wins.

When more than one online source answers for a comic (``first_wins`` off,
CLI ``--all-sources``, or a pinned id on each), the merge overlays them in
the reverse of ``online.lookup.sources``, so the first-listed source wins
every single-valued tag they disagree on. Unset, the order is
``SOURCE_NAMES``: Metron, then Comic Vine, then VerseDB. Lists and keyed
tags still combine from every source. Before, the merge took the
``MetadataSources`` enum order whatever the selection, and Comic Vine won
every disagreement.

One tag does not follow the order: each online source's own id. A source
is the authority on its own ids, so Metron's ``cv_id`` cross-reference
gives way to Comic Vine's own id whenever Comic Vine answered too.
"""

from __future__ import annotations

import itertools
from argparse import Namespace
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ONLINE_SOURCE_BY_NAME, ComicboxOnlineLookup
from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.formats.sources import MetadataSources
from comicbox.online_session import OnlineCredentials, OnlineSession
from tests.util.online_matcher import make_candidate

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from comicbox.config.settings import ComicboxSettings
    from comicbox.formats.base.online.profile import Candidate

_ALL_KEYS = OnlineCredentials(
    metron_key="k", comicvine_key="k", versedb_key="versedb-token"
)
_ORDERS = tuple(itertools.permutations(SOURCE_NAMES))

# What the comic's own tags say: enough for every fake source's one
# candidate (make_candidate's defaults) to be a sure match.
_PROFILE = MappingProxyType(
    {
        "comicbox": {
            "series": {"name": "Foo Comics"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
            "publisher": {"name": "Quality Comics"},
            "page_count": 24,
        }
    }
)


def _tags(name: str) -> dict[str, Any]:
    """One source's answer: a single-valued tag and a keyed one."""
    return {"title": f"title from {name}", "genres": {name: {}}}


def _merged(answering: Iterable[str], config: ComicboxSettings | None = None) -> dict:
    """Merge the named sources' answers, added in SOURCE_NAMES order."""
    with Comicbox(config=config) as cb:
        for name in SOURCE_NAMES:
            if name in answering:
                cb.add_source(
                    ONLINE_SOURCE_BY_NAME[name],
                    {"comicbox": _tags(name)},
                    fmt=MetadataFormats.COMICBOX_JSON,
                )
        return dict(cb.to_dict()["comicbox"])


def _selected(*names: str) -> ComicboxSettings:
    return get_config({"comicbox": {"online": {"lookup": {"sources": list(names)}}}})


##############
# The merge  #
##############


@pytest.mark.parametrize(
    ("answering", "winner"),
    [
        (SOURCE_NAMES, "metron"),
        (("metron", "comicvine"), "metron"),
        (("metron", "versedb"), "metron"),
        (("comicvine", "versedb"), "comicvine"),
    ],
)
def test_default_order_is_metron_then_comic_vine_then_versedb(
    answering: tuple[str, ...], winner: str
) -> None:
    """Nothing selected: SOURCE_NAMES order, and keyed tags still combine."""
    md = _merged(answering)
    assert md["title"] == f"title from {winner}"
    assert set(md["genres"]) == set(answering)


@pytest.mark.parametrize("order", _ORDERS, ids="-".join)
def test_the_first_selected_source_wins(order: tuple[str, ...]) -> None:
    """
    Every selected order ranks its sources first to last.

    Dropping each winner's answer in turn shows the next one beats the
    rest, so the whole order holds, not just its head.
    """
    config = _selected(*order)
    for rank, winner in enumerate(order):
        md = _merged(order[rank:], config)
        assert md["title"] == f"title from {winner}"
        assert set(md["genres"]) == set(order[rank:])


@pytest.mark.parametrize("unselected", SOURCE_NAMES)
def test_an_unselected_source_loses_to_every_selected_one(unselected: str) -> None:
    """
    Answers from a source outside the selection rank below it.

    A lookup only runs selected sources, so only a direct ``add_source``
    can put them there.
    """
    selected = tuple(name for name in SOURCE_NAMES if name != unselected)
    config = _selected(*selected)
    for name in selected:
        assert _merged((unselected, name), config)["title"] == f"title from {name}"


def test_unselected_sources_keep_the_default_order_among_themselves() -> None:
    assert _merged(("metron", "comicvine"), _selected("versedb"))["title"] == (
        "title from metron"
    )


def test_an_explicit_merge_order_beats_the_selection() -> None:
    """
    ``read.merge_order`` is the whole order; the selection does not move it.

    Comic Vine wins although the selection puts it last and the default
    puts Metron first.
    """
    config = get_config(
        {
            "comicbox": {
                "read": {"merge_order": ["VERSEDB_API", "METRON_API", "COMICVINE_API"]},
                "online": {"lookup": {"sources": ["versedb", "metron", "comicvine"]}},
            }
        }
    )
    assert _merged(SOURCE_NAMES, config)["title"] == "title from comicvine"


def test_the_enum_lists_the_online_sources_in_default_precedence() -> None:
    """
    The enum's online block is SOURCE_NAMES reversed, later winning.

    Print and validate walk the enum, and ``read.merge_order`` appends
    unlisted sources in enum order, so they agree with the default. A
    fourth source added in the wrong slot fails here.
    """
    online_sources = frozenset(ONLINE_SOURCE_BY_NAME.values())
    in_enum = [source for source in MetadataSources if source in online_sources]
    assert in_enum == [ONLINE_SOURCE_BY_NAME[name] for name in reversed(SOURCE_NAMES)]


def test_the_default_run_order_is_source_names() -> None:
    """The factory map, which sets the run order unselected, is SOURCE_NAMES."""
    assert tuple(ONLINE_SOURCE_BY_NAME) == SOURCE_NAMES
    assert tuple(ComicboxOnlineLookup._ONLINE_SOURCE_FACTORIES) == SOURCE_NAMES


#####################################
# Through a lookup with fake sources #
#####################################


class _SureSource:
    """A fake source whose one candidate is a sure match; get() answers payload."""

    def __init__(
        self,
        name: str,
        payload: Mapping[str, Any],
        fmt: MetadataFormats = MetadataFormats.COMICBOX_JSON,
    ) -> None:
        self.name = name
        self.metadata_source = ONLINE_SOURCE_BY_NAME[name]
        self.metadata_format = fmt
        self._payload = payload
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return True

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return dict(self._payload)

    def search(self, profile) -> list[Candidate]:
        return [replace(make_candidate(issue_id=101), source=self.name)]

    def enrich_prompt_candidates(self, candidates) -> tuple[Candidate, ...]:
        return tuple(candidates)


def _install(monkeypatch: pytest.MonkeyPatch, *sources: _SureSource) -> None:
    """Make the lookup build these sources, in this default order."""
    factories = {
        source.name: (lambda _creds, _settings, source=source: source)
        for source in sources
    }
    monkeypatch.setattr(
        ComicboxOnlineLookup, "_ONLINE_SOURCE_FACTORIES", MappingProxyType(factories)
    )


@pytest.fixture
def sure_sources(monkeypatch: pytest.MonkeyPatch) -> dict[str, _SureSource]:
    """Install a sure source per name, and open the session's files pathless."""
    sources = {name: _SureSource(name, _tags(name)) for name in SOURCE_NAMES}
    _install(monkeypatch, *sources.values())

    def pathless_box(_path: Path, config: ComicboxSettings) -> Comicbox:
        general = replace(config.general, metadata=_PROFILE)
        return Comicbox(config=replace(config, general=general))

    monkeypatch.setattr("comicbox.online_session.Comicbox", pathless_box)
    return sources


@pytest.mark.parametrize("order", _ORDERS, ids="-".join)
def test_a_sessions_source_order_reaches_the_merge(
    tmp_path: Path, sure_sources: dict[str, _SureSource], order: tuple[str, ...]
) -> None:
    """``OnlineSession(sources=...)`` with first_wins off: its order wins."""
    session = OnlineSession(sources=order, credentials=_ALL_KEYS, first_wins=False)
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert [sure_sources[name].get_calls for name in order] == [[101]] * 3
    assert result.tags is not None
    assert result.tags["title"] == f"title from {order[0]}"
    assert set(result.tags["genres"]) == set(SOURCE_NAMES)


def test_first_wins_still_ends_the_lookup_at_the_first_match(
    tmp_path: Path, sure_sources: dict[str, _SureSource]
) -> None:
    session = OnlineSession(
        sources=("comicvine", "metron", "versedb"), credentials=_ALL_KEYS
    )
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert sure_sources["comicvine"].get_calls == [101]
    assert sure_sources["metron"].get_calls == []
    assert sure_sources["versedb"].get_calls == []
    assert result.tags is not None
    assert result.tags["title"] == "title from comicvine"
    assert set(result.tags["genres"]) == {"comicvine"}


_METRON_ISSUE = MappingProxyType(
    {
        "id": 42,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "series": {"id": 100, "name": "Foo Comics", "year_began": 2018, "volume": 1},
        "cv_id": 999,  # Metron's cross-reference to Comic Vine
    }
)
_COMIC_VINE_ISSUE = MappingProxyType(
    {
        "id": 1234,
        "number": "5",
        "cover_date": "2020-04-01",
        "date_last_updated": "2020-04-02T12:00:00Z",
        "volume": {"id": 50, "name": "Foo Comics"},
    }
)


@pytest.mark.parametrize(
    "online_sources",
    [["all"], ["comicvine", "metron"]],
    ids=["default", "comicvine-first"],
)
def test_comic_vine_keeps_its_own_id_whoever_wins(
    monkeypatch: pytest.MonkeyPatch, online_sources: list[str]
) -> None:
    """
    Comic Vine's own id beats Metron's stored ``cv_id``, in either order.

    Metron winning wrote its cross-reference, and the next run refreshed
    Comic Vine by that id without searching, so a stale one took over the
    comic for good and the warning went quiet. The link follows the id
    kept, and the cross-source check still warns.
    """
    _install(
        monkeypatch,
        _SureSource("metron", _METRON_ISSUE, MetadataFormats.METRON_API),
        _SureSource("comicvine", _COMIC_VINE_ISSUE, MetadataFormats.COMICVINE_API),
    )
    warnings: list[str] = []
    monkeypatch.setattr("comicbox.box.online_lookup.logger.warning", warnings.append)
    args = Namespace(
        comicbox=Namespace(
            online_sources=online_sources,
            all_sources=True,
            auth=["metron:key=k", "comicvine:key=k"],
            general=Namespace(metadata=dict(_PROFILE)),
        )
    )
    with Comicbox(config=args) as cb:
        md = cb.to_dict()["comicbox"]
    assert md["identifiers"]["comicvine"] == {"key": "1234"}
    assert md["identifiers"]["metron"] == {"key": "42"}
    assert "https://comicvine.gamespot.com/c/4000-1234/" in md["urls"]
    assert "https://comicvine.gamespot.com/c/4000-999/" not in md["urls"]
    assert any("cross-source" in warning for warning in warnings)


def _merged_ids(answers: Mapping[str, Mapping], patch: Mapping | None = None) -> dict:
    """Merge online answers' identifiers, and a caller's patch over them."""
    with Comicbox(metadata=patch) as cb:
        for name, identifiers in answers.items():
            cb.add_source(
                ONLINE_SOURCE_BY_NAME[name],
                {"comicbox": {"identifiers": identifiers}},
                fmt=MetadataFormats.COMICBOX_JSON,
            )
        return dict(cb.to_dict()["comicbox"]["identifiers"])


_METRON_IDS = MappingProxyType({"metron": {"key": "42"}, "comicvine": {"key": "999"}})


def test_metrons_cross_reference_fills_the_gap_when_comic_vine_is_silent() -> None:
    assert _merged_ids({"metron": _METRON_IDS})["comicvine"] == {"key": "999"}


def test_a_patch_still_beats_comic_vines_own_id() -> None:
    patch = {"comicbox": {"identifiers": {"comicvine": {"key": "555"}}}}
    answers = {"metron": _METRON_IDS, "comicvine": {"comicvine": {"key": "1234"}}}
    assert _merged_ids(answers, patch)["comicvine"] == {"key": "555"}
