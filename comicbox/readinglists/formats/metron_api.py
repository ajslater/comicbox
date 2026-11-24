"""
Reading lists built from Metron's reading lists and story arcs.

Builders from mokkari objects, read by attribute, so this module imports no
network library. Metron is a source, not a format: nothing is written back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from comicbox.empty import is_empty
from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.online.sanitize import strip_html
from comicbox.formats.base.online.transform_helpers import build_identifier
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    SERIES_START_YEAR_KEY,
    STORE_DATE_KEY,
)
from comicbox.readinglists.arcs import STORY_LIST_TYPE
from comicbox.readinglists.schema import (
    DATE_KEY,
    DESCRIPTION_KEY,
    ENTRIES_KEY,
    ENTRY_TYPE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    NEXT_KEY,
    NUMBER_KEY,
    ORDERED_KEY,
    PREVIOUS_KEY,
    PRIVATE_KEY,
    SERIES_KEY,
    SOURCE_CURATOR_KEY,
    SOURCE_CURATOR_URL_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_REVISION_KEY,
    SOURCE_URL_KEY,
    SOURCES_KEY,
    VOLUME_KEY,
    SourceKind,
)
from comicbox.readinglists.serialize import ReadingListResult, load_model_with_warnings

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from datetime import datetime

    from mokkari.schemas.arc import Arc
    from mokkari.schemas.issue import BaseIssue, BasicSeries
    from mokkari.schemas.reading_list import (
        ReadingListIssue,
        ReadingListItem,
        ReadingListList,
        ReadingListNav,
        ReadingListRead,
    )

_METRON = IdSources.METRON.value
_COMICVINE = IdSources.COMICVINE.value
_GCD = IdSources.GCD.value


@dataclass(frozen=True, slots=True)
class MetronListSummary:
    """
    One reading list a Metron search found.

    ``curator`` is the site the list was taken from, lowercased like a
    fetched list's source, or None. ``rating`` is the average of
    ``rating_count`` ratings, or None when there are none.
    """

    id: int
    name: str
    list_type: str
    private: bool
    curator: str | None
    username: str
    rating: float | None
    rating_count: int
    modified: datetime


def summary_from_metron(row: ReadingListList) -> MetronListSummary:
    """Summarize one row of ``reading_lists_list``."""
    curator = row.attribution_source
    return MetronListSummary(
        id=row.id,
        name=row.name,
        list_type=row.list_type,
        private=row.is_private,
        curator=curator.value.lower() if curator else None,
        username=row.user.username,
        rating=row.average_rating,
        rating_count=row.rating_count,
        modified=row.modified,
    )


def _without_empty(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if not is_empty(value)}


def _series(series: BasicSeries) -> dict[str, Any]:
    return {
        NAME_KEY: series.name,
        SERIES_START_YEAR_KEY: series.year_began,
        IDENTIFIERS_KEY: {_METRON: build_identifier(_METRON, "series", series.id)},
    }


def _entry(
    issue: ReadingListIssue | BaseIssue, identifiers: dict[str, Any]
) -> dict[str, Any]:
    dates = {COVER_DATE_KEY: issue.cover_date, STORE_DATE_KEY: issue.store_date}
    return _without_empty(
        {
            SERIES_KEY: _series(issue.series),
            VOLUME_KEY: {NUMBER_KEY: issue.series.volume},
            ISSUE_KEY: {NAME_KEY: issue.number},
            DATE_KEY: _without_empty(dates),
            IDENTIFIERS_KEY: identifiers,
        }
    )


def _item_entry(item: ReadingListItem) -> dict[str, Any]:
    issue = item.issue
    ids = {_METRON: issue.id, _COMICVINE: issue.cv_id, _GCD: issue.gcd_id}
    identifiers = {
        source: build_identifier(source, "issue", value)
        for source, value in ids.items()
        if value is not None
    }
    entry = _entry(issue, identifiers)
    if item.issue_type:
        entry[ENTRY_TYPE_KEY] = item.issue_type
    return entry


def _list_reference(nav: ReadingListNav | None) -> dict[str, Any] | None:
    if nav is None:
        return None
    return {
        NAME_KEY: nav.name,
        SOURCE_KIND_KEY: SourceKind.METRON_LIST.value,
        SOURCE_KEY_KEY: str(nav.id),
    }


def _load(raw: dict[str, Any]) -> ReadingListResult:
    reading_list, warnings = load_model_with_warnings(_without_empty(raw))
    return ReadingListResult(reading_list, None, warnings)


def reading_list_from_metron(
    header: ReadingListRead, items: Iterable[ReadingListItem]
) -> ReadingListResult:
    """
    Build a list from a Metron reading list and its items.

    Items run in their ``order``, those without one last, each group in the
    order the API sent them.
    """
    source = {
        SOURCE_KIND_KEY: SourceKind.METRON_LIST.value,
        SOURCE_KEY_KEY: str(header.id),
        SOURCE_URL_KEY: header.resource_url,
        SOURCE_REVISION_KEY: header.modified.isoformat(),
        SOURCE_CURATOR_KEY: header.attribution_source.lower(),
        SOURCE_CURATOR_URL_KEY: header.attribution_url and str(header.attribution_url),
    }
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (pair[1].order is None, pair[1].order or 0, pair[0]),
    )
    return _load(
        {
            NAME_KEY: header.name,
            DESCRIPTION_KEY: strip_html(header.desc),
            LIST_TYPE_KEY: header.list_type,
            ORDERED_KEY: True,
            # Only a private list says so: a public one has nothing to lose.
            PRIVATE_KEY: header.is_private or None,
            SOURCES_KEY: [_without_empty(source)],
            PREVIOUS_KEY: _list_reference(header.previous),
            NEXT_KEY: _list_reference(header.next),
            ENTRIES_KEY: [_item_entry(item) for _, item in ranked],
        }
    )


def reading_list_from_metron_arc(
    arc: Arc, issues: Iterable[BaseIssue]
) -> ReadingListResult:
    """
    Build an unordered story list from a Metron arc and its issues.

    The arc's issue list carries Metron ids only (F8). An arc that names its
    Comic Vine arc also gets a pointer source to it.
    """
    sources = [
        {
            SOURCE_KIND_KEY: SourceKind.METRON_ARC.value,
            SOURCE_KEY_KEY: str(arc.id),
            SOURCE_URL_KEY: str(arc.resource_url),
            SOURCE_REVISION_KEY: arc.modified.isoformat(),
        }
    ]
    if arc.cv_id:
        sources.append(
            {
                SOURCE_KIND_KEY: SourceKind.COMICVINE_ARC.value,
                SOURCE_KEY_KEY: str(arc.cv_id),
            }
        )
    entries = [
        _entry(issue, {_METRON: build_identifier(_METRON, "issue", issue.id)})
        for issue in issues
    ]
    return _load(
        {
            NAME_KEY: arc.name,
            DESCRIPTION_KEY: strip_html(arc.desc),
            LIST_TYPE_KEY: STORY_LIST_TYPE,
            ORDERED_KEY: False,
            SOURCES_KEY: sources,
            ENTRIES_KEY: entries,
        }
    )
