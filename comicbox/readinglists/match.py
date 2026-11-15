"""
Match a reading list against the comics in a directory.

Each comic becomes an entry with ``entry_from_comic``. An entry is found by
its ids first, then by its strict name key, then by its name variants in
order; the cover year breaks ties. An entry with no key matches nothing.
The matching is pure; reading the directory is separate.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from comicbox.constants import ROOT_TAG
from comicbox.formats.comicbox.schema import ARCS_KEY
from comicbox.readinglists.arcs import entry_from_comic
from comicbox.readinglists.combine.fields import is_ordered
from comicbox.readinglists.identity import (
    ID_KEY_KIND,
    EntryKey,
    entry_date,
    entry_keys,
    variant_keys,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NUMBER_KEY


class FoundBy(StrEnum):
    """How an entry was found: the strength of the key that matched."""

    ID = "id"
    NAME = "name"
    VARIANT = "variant"


@dataclass(frozen=True, slots=True)
class Found:
    """The comics that are entry ``position`` (from 0), and how they matched."""

    position: int
    paths: tuple[Path, ...]
    by: FoundBy


@dataclass(frozen=True, slots=True)
class MatchResult:
    """What a directory has of a list, and what it is missing, by position."""

    found: tuple[Found, ...]
    missing: tuple[int, ...]


def _year(entry: Mapping[str, Any]) -> int | None:
    """Get an entry's cover year; a date that did not parse has none."""
    when = entry_date(entry)
    return when.year if isinstance(when, date) else None


class _Index:
    """The comics, by every key that can find them."""

    def __init__(self, comics: Mapping[Path, Mapping[str, Any]]) -> None:
        self.ids: defaultdict[EntryKey, list[Path]] = defaultdict(list)
        self.names: defaultdict[EntryKey, list[Path]] = defaultdict(list)
        self.variants: defaultdict[EntryKey, list[Path]] = defaultdict(list)
        self.years: dict[Path, int | None] = {}
        for path in sorted(comics):
            entry = entry_from_comic(comics[path])
            self.years[path] = _year(entry)
            for key in entry_keys(entry):
                (self.ids if key[0] == ID_KEY_KIND else self.names)[key].append(path)
            for key in variant_keys(entry):
                self.variants[key].append(path)

    def _tie_break(self, paths: list[Path], year: int | None) -> tuple[Path, ...]:
        """Keep the comics of the entry's year, when that tells them apart."""
        if year is not None and len(paths) > 1:
            same_year = [path for path in paths if self.years[path] == year]
            if same_year:
                return tuple(same_year)
        return tuple(paths)

    def find(self, entry: Mapping[str, Any]) -> tuple[tuple[Path, ...], FoundBy] | None:
        """Find an entry's comics by its strongest key that matches any."""
        year = _year(entry)
        keys = entry_keys(entry)
        searches: Iterable[tuple[EntryKey, Mapping[EntryKey, list[Path]], FoundBy]] = (
            *((key, self.ids, FoundBy.ID) for key in keys if key[0] == ID_KEY_KIND),
            *((key, self.names, FoundBy.NAME) for key in keys if key[0] != ID_KEY_KIND),
            *((key, self.variants, FoundBy.VARIANT) for key in variant_keys(entry)),
        )
        for key, index, by in searches:
            if paths := index.get(key):
                return self._tie_break(paths, year), by
        return None


def match_comics(
    reading_list: Mapping[str, Any], comics: Mapping[Path, Mapping[str, Any]]
) -> MatchResult:
    """
    Find each of a list's entries among some comics' tags.

    ``comics`` maps each comic's path to its tags, as a ``ReadResult``
    holds them. A comic of one issue in several files is found in all.
    """
    index = _Index(comics)
    found: list[Found] = []
    missing: list[int] = []
    for position, entry in enumerate(reading_list.get(ENTRIES_KEY) or ()):
        if (hit := index.find(entry)) is None:
            missing.append(position)
        else:
            found.append(Found(position, *hit))
    return MatchResult(tuple(found), tuple(missing))


# Arcs.


class ArcAction(StrEnum):
    """What tagging one comic with a list's arc would do."""

    ADD = "add"
    RENUMBER = "renumber"
    TAGGED = "tagged"


@dataclass(frozen=True, slots=True)
class ArcChange:
    """
    The arc one comic should carry, and what it carries now.

    ``arc`` is the name to write under: the comic's own spelling when it
    already has the arc in another case, so it never gets the arc twice.
    ``number`` is None for an unordered list. ``current`` is the number the
    comic has, when it has the arc.
    """

    path: Path
    arc: str
    number: int | None
    action: ArcAction
    current: int | None = None


def _current_arc(
    tags: Mapping[str, Any], name: str
) -> tuple[str, Mapping[str, Any]] | None:
    """Find a comic's arc of this name, in any case."""
    arcs = tags.get(ARCS_KEY) or {}
    folded = name.casefold()
    for arc_name, arc in arcs.items():
        if str(arc_name).casefold() == folded:
            return str(arc_name), arc if isinstance(arc, Mapping) else {}
    return None


def _change(
    path: Path, tags: Mapping[str, Any], name: str, number: int | None
) -> ArcChange:
    if (current := _current_arc(tags, name)) is None:
        return ArcChange(path, name, number, ArcAction.ADD)
    arc_name, arc = current
    has = arc.get(NUMBER_KEY)
    # An unordered list has no number to set, so having the arc is enough.
    if number is None or has == number:
        return ArcChange(path, arc_name, number, ArcAction.TAGGED, has)
    return ArcChange(path, arc_name, number, ArcAction.RENUMBER, has)


def plan_arcs(
    reading_list: Mapping[str, Any],
    comics: Mapping[Path, Mapping[str, Any]],
    result: MatchResult,
    name: str,
) -> tuple[ArcChange, ...]:
    """
    Plan the arc each found comic should carry, in path order.

    The arc is named ``name``; its number is the entry's place in an
    ordered list, the first place for an issue the list reads twice.
    """
    ordered = is_ordered(reading_list)
    numbers: dict[Path, int | None] = {}
    for found in result.found:
        for path in found.paths:
            numbers.setdefault(path, found.position + 1 if ordered else None)
    return tuple(
        _change(path, _tags(comics[path]), name, numbers[path])
        for path in sorted(numbers)
    )


def _tags(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = metadata.get(ROOT_TAG)
    return inner if isinstance(inner, Mapping) else metadata


# Reading a directory.


class _Unlogged:
    """
    A logger that drops the reader's own reports of failed comics.

    ``read_comics`` hands each failure to its caller, which reports it once;
    the reader would otherwise log it again.
    """

    def warning(self, *_args: object, **_kwargs: object) -> None:
        """Drop a failed comic's warning."""

    def exception(self, *_args: object, **_kwargs: object) -> None:
        """Drop a failed comic's traceback."""


def read_comics(
    directory: Path,
    config: Any = None,
    on_error: Callable[[Path, BaseException], None] | None = None,
) -> dict[Path, dict[str, Any]]:
    """
    Read the tags of every comic under a directory, in path order.

    A comic that cannot be read goes to ``on_error`` and the rest are read.
    A comic with no tags is left out: there is nothing to match it by.
    """
    from comicbox.process import iter_process_files
    from comicbox.run import iter_recurse

    tags: dict[Path, dict[str, Any]] = {}
    reads = iter_process_files(iter_recurse(directory), config, logger=_Unlogged())
    for path, (result, error) in reads:
        if error is not None:
            if on_error is not None:
                on_error(path, error)
        elif result["tags"]:
            tags[path] = result["tags"]
    return {path: tags[path] for path in sorted(tags)}
