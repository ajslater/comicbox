"""
Reading lists built from Comic Vine story arcs.

A builder from simyan objects, read by attribute, so this module imports no
network library. Comic Vine is a source, not a format: nothing is written back.
"""

from __future__ import annotations

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
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    ORDERED_KEY,
    SERIES_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_REVISION_KEY,
    SOURCE_URL_KEY,
    SOURCES_KEY,
    SourceKind,
)
from comicbox.readinglists.serialize import ReadingListResult, load_model_with_warnings

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from simyan.schemas.issue import BasicIssue
    from simyan.schemas.story_arc import StoryArc
    from simyan.schemas.volume import BasicVolume

_COMICVINE = IdSources.COMICVINE.value


def _without_empty(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if not is_empty(value)}


def _identifiers(id_type: str, value: int) -> dict[str, Any]:
    return {_COMICVINE: build_identifier(_COMICVINE, id_type, value)}


def _series(issue: BasicIssue, volume: BasicVolume | None) -> dict[str, Any]:
    """Name the issue's volume as its series; the volume's row has the year."""
    return _without_empty(
        {
            NAME_KEY: volume.name if volume else issue.volume.name,
            SERIES_START_YEAR_KEY: volume.start_year if volume else None,
            IDENTIFIERS_KEY: _identifiers("series", issue.volume.id),
        }
    )


def _entry(
    issue_id: int, issue: BasicIssue | None, volumes: Mapping[int, BasicVolume]
) -> dict[str, Any]:
    """
    Describe one member of the arc.

    Comic Vine's ``name`` for an issue is its story title, which an entry
    has no place for; the issue number is the entry's issue name, as
    Metron's is.
    """
    identifiers = _identifiers("issue", issue_id)
    if issue is None:
        # No row came back for it: it stays a member, known by its id.
        return {IDENTIFIERS_KEY: identifiers}
    dates = {COVER_DATE_KEY: issue.cover_date, STORE_DATE_KEY: issue.store_date}
    return _without_empty(
        {
            SERIES_KEY: _series(issue, volumes.get(issue.volume.id)),
            ISSUE_KEY: _without_empty({NAME_KEY: issue.number}),
            DATE_KEY: _without_empty(dates),
            IDENTIFIERS_KEY: identifiers,
        }
    )


def reading_list_from_comicvine_arc(
    arc: StoryArc,
    issues: Iterable[BasicIssue] = (),
    volumes: Iterable[BasicVolume] = (),
) -> ReadingListResult:
    """
    Build an unordered story list from a Comic Vine arc.

    The arc names its issues by id alone. ``issues`` and ``volumes`` are
    the rows for those issues and their volumes, which give each entry its
    series, start year, number and dates. Every member of the arc gets an
    entry, in the arc's order, whether a row came for it or not. Comic Vine
    states no reading order for an arc, so the list is unordered.

    The revision is the arc's ``date_last_updated`` as Comic Vine gives it,
    with no time zone: Comic Vine states none, and a revision is only ever
    compared with another from the same source.
    """
    rows = {issue.id: issue for issue in issues}
    volume_rows = {volume.id: volume for volume in volumes}
    source = {
        SOURCE_KIND_KEY: SourceKind.COMICVINE_ARC.value,
        SOURCE_KEY_KEY: str(arc.id),
        SOURCE_URL_KEY: str(arc.site_url),
        SOURCE_REVISION_KEY: arc.date_last_updated.isoformat(),
    }
    entries = [
        _entry(member.id, rows.get(member.id), volume_rows) for member in arc.issues
    ]
    raw = {
        NAME_KEY: arc.name,
        # The deck is Comic Vine's one-line summary, for an arc with no
        # long description.
        DESCRIPTION_KEY: strip_html(arc.description) or arc.summary,
        LIST_TYPE_KEY: STORY_LIST_TYPE,
        ORDERED_KEY: False,
        SOURCES_KEY: [source],
        ENTRIES_KEY: entries,
    }
    reading_list, warnings = load_model_with_warnings(_without_empty(raw))
    return ReadingListResult(reading_list, None, warnings)
