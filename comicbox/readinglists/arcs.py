"""
Arc tags and reading lists.

A comic's ``arcs`` tag, ``{name: {number}}``, is a per-comic view of list
membership. These functions go both ways: the entry that refers to a comic,
the lists a set of comics' arc tags describe, and the patch that tags one
comic as part of a list.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from comicbox.constants import ROOT_TAG
from comicbox.empty import is_empty
from comicbox.enums.comicbox import IdSources
from comicbox.formats.comicbox.schema import (
    ARCS_KEY,
    COVER_DATE_KEY,
    ISSUE_SUFFIX_KEY,
    SERIES_START_YEAR_KEY,
    YEAR_KEY,
)
from comicbox.identifiers import ID_KEY_KEY
from comicbox.readinglists.combine.groups import group_rows
from comicbox.readinglists.identity import entry_sort_key
from comicbox.readinglists.schema import (
    DATE_KEY,
    ENTRIES_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    ORDERED_KEY,
    SERIES_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCES_KEY,
    VOLUME_KEY,
    SourceKind,
)
from comicbox.readinglists.serialize import load_model

STORY_LIST_TYPE = "story"
# The database an arc id names -> the kind of list it points to, best
# ranked source first.
_ARC_POINTER_KINDS: MappingProxyType[str, SourceKind] = MappingProxyType(
    {
        IdSources.METRON.value: SourceKind.METRON_ARC,
        IdSources.COMICVINE.value: SourceKind.COMICVINE_ARC,
    }
)
_SERIES_KEYS = (NAME_KEY, SERIES_START_YEAR_KEY, IDENTIFIERS_KEY)
_ISSUE_KEYS = (NAME_KEY, NUMBER_KEY, ISSUE_SUFFIX_KEY)
_DATE_KEYS = (COVER_DATE_KEY, YEAR_KEY)


def _plain(value: Any) -> Any:
    """Deep copy mappings and sequences into dicts and lists."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _pick(data: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Pick the non-empty values of some keys."""
    if not isinstance(data, Mapping):
        return {}
    return {key: _plain(data[key]) for key in keys if not is_empty(data.get(key))}


def _comic(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept a comic wrapped in its root tag or the inner mapping."""
    inner = metadata.get(ROOT_TAG)
    return inner if isinstance(inner, Mapping) else metadata


def entry_from_comic(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build the entry that refers to a comic.

    Takes ``{"comicbox": {...}}`` or the inner mapping, which is what a
    ``ReadResult``'s ``tags`` holds. Keeps the series name, start year and
    ids, the volume number, the issue, the cover date and year, and the
    issue-level ids.
    """
    comic = _comic(metadata)
    entry: dict[str, Any] = {}
    if series := _pick(comic.get(SERIES_KEY), _SERIES_KEYS):
        entry[SERIES_KEY] = series
    if volume := _pick(comic.get(VOLUME_KEY), (NUMBER_KEY,)):
        entry[VOLUME_KEY] = volume
    if issue := _pick(comic.get(ISSUE_KEY), _ISSUE_KEYS):
        entry[ISSUE_KEY] = issue
    if entry_date := _pick(comic.get(DATE_KEY), _DATE_KEYS):
        entry[DATE_KEY] = entry_date
    if identifiers := comic.get(IDENTIFIERS_KEY):
        entry[IDENTIFIERS_KEY] = _plain(identifiers)
    return entry


class _ArcMembers:
    """The comics tagged with one arc, gathered for a list."""

    __slots__ = ("arc_ids", "comics", "name")

    def __init__(self, name: str) -> None:
        """Keep the first spelling of the name seen."""
        self.name = name
        self.comics: list[tuple[int | None, dict[str, Any]]] = []
        self.arc_ids: dict[str, list[str]] = {}

    def add(self, entry: dict[str, Any], arc: Mapping[str, Any]) -> None:
        """Add a comic's entry and remember the ids its arc tag carries."""
        self.comics.append((arc.get(NUMBER_KEY), entry))
        for source, identifier in (arc.get(IDENTIFIERS_KEY) or {}).items():
            if source in _ARC_POINTER_KINDS and (
                key := (identifier or {}).get(ID_KEY_KEY)
            ):
                self.arc_ids.setdefault(source, []).append(str(key))

    def _sources(self) -> list[dict[str, str]]:
        """List the tags source, then a pointer to each database's arc."""
        sources = [{SOURCE_KIND_KEY: SourceKind.TAGS.value}]
        for source, kind in _ARC_POINTER_KINDS.items():
            if keys := self.arc_ids.get(source):
                # The most common id wins; a tie goes to the first seen.
                key = Counter(keys).most_common(1)[0][0]
                sources.append({SOURCE_KIND_KEY: kind.value, SOURCE_KEY_KEY: key})
        return sources

    def _members(self) -> list[tuple[int | None, dict[str, Any]]]:
        """
        Fold copies of one issue into the first seen, by ``combine``'s rule.

        Each comic is a list of one row: the rows ``combine`` would join are
        copies of one issue.
        """
        grouping = group_rows([[entry] for _, entry in self.comics])
        return [self.comics[members[0][0]] for members in grouping.members]

    def reading_list(self) -> dict[str, Any]:
        """Build the list, ordered only when every member has its own number."""
        members = self._members()
        numbers = [number for number, _ in members]
        ordered = None not in numbers and len(set(numbers)) == len(numbers)
        members = sorted(
            members,
            key=lambda member: (
                member[0] is None,
                member[0] or 0,
                *entry_sort_key(member[1]),
            ),
        )
        return load_model(
            {
                NAME_KEY: self.name,
                LIST_TYPE_KEY: STORY_LIST_TYPE,
                ORDERED_KEY: ordered,
                SOURCES_KEY: self._sources(),
                ENTRIES_KEY: [entry for _, entry in members],
            }
        )


def reading_lists_from_comics(
    comics: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build one list per arc that a set of comics is tagged with.

    Arc names group case-insensitively and keep the first spelling seen.
    Copies of one issue are one entry. Entries go by arc number, then cover
    date, series and issue. Lists come back sorted by name.
    """
    arcs: dict[str, _ArcMembers] = {}
    for metadata in comics:
        comic = _comic(metadata)
        if not (comic_arcs := comic.get(ARCS_KEY)):
            continue
        entry = entry_from_comic(comic)
        for name, arc in comic_arcs.items():
            members = arcs.setdefault(name.casefold(), _ArcMembers(name))
            members.add(entry, arc or {})
    return [arcs[folded].reading_list() for folded in sorted(arcs)]


def arc_patch(list_name: str, number: int | None = None) -> dict[str, Any]:
    """
    Build the patch that tags one comic as part of a list.

    For ``write_metadata`` with ``merge_mode="additive"``, so the patch adds
    the arc and keeps the comic's others; under ``update`` it would replace
    them.
    """
    arc = {} if number is None else {NUMBER_KEY: number}
    return {ARCS_KEY: {list_name: arc}}
