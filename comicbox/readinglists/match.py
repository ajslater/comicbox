"""
Match a reading list against the comics in a directory.

Each comic becomes an entry with ``entry_from_comic``. Matching goes in two
passes. First every entry takes each comic it shares a strict key with
(``entry_keys``: an issue id, the series name, start year or volume and
issue, or, weakest, the series name, cover year and issue). Then each entry that found none tries its name variants in order,
among the comics no entry took strictly. Either way a comic is refused when
it carries an id from a database the entry has a different id from, or a
cover year more than a year off the entry's; found by the cover year alone,
also when its series year differs from the entry's. An entry with no key matches
nothing. The matching is pure; reading the directory is separate.
"""

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from comicbox.constants import ROOT_TAG
from comicbox.formats.comicbox.schema import ARCS_KEY
from comicbox.readinglists.arcs import entry_from_comic
from comicbox.readinglists.combine.fields import is_ordered
from comicbox.readinglists.identity import (
    ID_KEY_KIND,
    NAME_YEAR_KEY_KIND,
    EntryKey,
    entry_date,
    entry_keys,
    series_year,
    variant_keys,
)
from comicbox.readinglists.schema import ENTRIES_KEY, NUMBER_KEY

# Cover years further apart than this are two different issues.
_COVER_YEAR_SLACK = 1


class FoundBy(StrEnum):
    """How a comic was found: the strength of the key that matched."""

    ID = "id"
    NAME = "name"
    NAME_YEAR = "name-year"
    VARIANT = "variant"

    @property
    def strict(self) -> bool:
        """Whether this is an ``entry_keys`` match, not a name variant."""
        return self is not FoundBy.VARIANT


# How a key's kind finds a comic; every other strict key is a name.
_FOUND_BY_KIND = MappingProxyType(
    {ID_KEY_KIND: FoundBy.ID, NAME_YEAR_KEY_KIND: FoundBy.NAME_YEAR}
)


@dataclass(frozen=True, slots=True)
class FoundComic:
    """One comic an entry was found in, and how."""

    path: Path
    by: FoundBy


@dataclass(frozen=True, slots=True)
class Found:
    """
    The comics that are entry ``position`` (from 0), in path order.

    ``volumes`` holds the series years of the comics when the entry was
    found by its cover-year key alone and they hold more than one: the
    entry fits comics of several volumes, and ``match`` does not choose.
    """

    position: int
    comics: tuple[FoundComic, ...]
    volumes: tuple[int, ...] = ()

    @property
    def ambiguous(self) -> bool:
        """Whether the entry fits comics of more than one volume."""
        return bool(self.volumes)

    @property
    def paths(self) -> tuple[Path, ...]:
        """Get the paths of the comics found."""
        return tuple(comic.path for comic in self.comics)


@dataclass(frozen=True, slots=True)
class MatchResult:
    """What a directory has of a list, and what it is missing, by position."""

    found: tuple[Found, ...]
    missing: tuple[int, ...]


def _year(entry: Mapping[str, Any]) -> int | None:
    """Get an entry's cover year; a date that did not parse has none."""
    when = entry_date(entry)
    return when.year if isinstance(when, date) else None


@dataclass(frozen=True, slots=True)
class _Facts:
    """
    What vetoes a match: an entry's or comic's issue ids and cover year.

    And its series year, which vetoes a match on the cover-year key alone.
    """

    ids: Mapping[str, str]
    year: int | None
    series_year: int | None

    @classmethod
    def of(cls, entry: Mapping[str, Any], keys: Sequence[EntryKey]) -> "_Facts":
        ids = {key[1]: key[2] for key in keys if key[0] == ID_KEY_KIND}
        return cls(ids, _year(entry), series_year(entry))

    def other_volume(self, other: "_Facts") -> bool:
        """Tell whether both sides name a series year, and not the same one."""
        return (
            self.series_year is not None
            and other.series_year is not None
            and self.series_year != other.series_year
        )

    def contradicts(self, other: "_Facts") -> bool:
        """Tell whether two sides cannot be one issue, whatever their keys."""
        for source, key in self.ids.items():
            if other.ids.get(source, key) != key:
                return True
        return (
            self.year is not None
            and other.year is not None
            and abs(self.year - other.year) > _COVER_YEAR_SLACK
        )


class _Index:
    """The comics, by every key that can find them."""

    def __init__(self, comics: Mapping[Path, Mapping[str, Any]]) -> None:
        self.strict: defaultdict[EntryKey, list[Path]] = defaultdict(list)
        self.variants: defaultdict[EntryKey, list[Path]] = defaultdict(list)
        self.facts: dict[Path, _Facts] = {}
        # Each comic's strict name key, telling one series from another.
        self.series: dict[Path, EntryKey | None] = {}
        for path in sorted(comics):
            entry = entry_from_comic(comics[path])
            keys = entry_keys(entry)
            self.facts[path] = _Facts.of(entry, keys)
            self.series[path] = next(
                (key for key in keys if key[0] != ID_KEY_KIND), None
            )
            for key in keys:
                self.strict[key].append(path)
            for key in variant_keys(entry):
                self.variants[key].append(path)

    def find_strict(self, entry: Mapping[str, Any]) -> tuple[FoundComic, ...]:
        """Find every comic that shares a strict key with an entry."""
        keys = entry_keys(entry)
        facts = _Facts.of(entry, keys)
        found: dict[Path, FoundBy] = {}
        # The strongest key comes first, so a comic found by two is found by it.
        for key in keys:
            by = _FOUND_BY_KIND.get(key[0], FoundBy.NAME)
            for path in self.strict.get(key, ()):
                comic = self.facts[path]
                if path in found or facts.contradicts(comic):
                    continue
                # The cover year joins rows lacking a series year, not volumes.
                if by is FoundBy.NAME_YEAR and facts.other_volume(comic):
                    continue
                found[path] = by
        return tuple(FoundComic(path, found[path]) for path in sorted(found))

    def volumes(self, comics: Sequence[FoundComic]) -> tuple[int, ...]:
        """
        Name the volumes an entry found by its cover year alone fits, if several.

        A comic with no series year names none, so copies of one volume, or
        such a comic beside them, are no choice to make.
        """
        if not comics or any(comic.by is not FoundBy.NAME_YEAR for comic in comics):
            return ()
        years = {
            year
            for comic in comics
            if (year := self.facts[comic.path].series_year) is not None
        }
        return tuple(sorted(years)) if len(years) > 1 else ()

    def find_variant(
        self, entry: Mapping[str, Any], taken: Collection[Path]
    ) -> tuple[FoundComic, ...]:
        """Find an entry by its first name variant that some untaken comic has."""
        facts = _Facts.of(entry, entry_keys(entry))
        for key in variant_keys(entry):
            paths = [
                path
                for path in self.variants.get(key, ())
                if path not in taken and not facts.contradicts(self.facts[path])
            ]
            if paths:
                return tuple(
                    FoundComic(path, FoundBy.VARIANT)
                    for path in self._tie_break(paths, facts.year)
                )
        return ()

    def _tie_break(self, paths: list[Path], year: int | None) -> list[Path]:
        """
        Keep the series with a comic of the entry's year, among several.

        Copies of one issue in one series are all kept, whatever their years.
        """
        if year is None or len({self.series[path] for path in paths}) <= 1:
            return paths
        same_year = {
            self.series[path] for path in paths if self.facts[path].year == year
        }
        return [path for path in paths if self.series[path] in same_year] or paths


def match_comics(
    reading_list: Mapping[str, Any], comics: Mapping[Path, Mapping[str, Any]]
) -> MatchResult:
    """
    Find each of a list's entries among some comics' tags.

    ``comics`` maps each comic's path to its tags, as a ``ReadResult``
    holds them. Strict matches are settled for the whole list first, so a
    comic one entry is strictly is never another entry's variant. A comic
    of one issue in several files is found in all, and an issue the list
    holds twice is found in the same comics both times. An entry found by
    its cover year alone in comics of several volumes is marked so.
    """
    index = _Index(comics)
    entries = tuple(reading_list.get(ENTRIES_KEY) or ())
    strict = [index.find_strict(entry) for entry in entries]
    taken = frozenset(comic.path for found in strict for comic in found)
    found: list[Found] = []
    missing: list[int] = []
    for position, (entry, comics_found) in enumerate(zip(entries, strict, strict=True)):
        if hits := comics_found or index.find_variant(entry, taken):
            found.append(Found(position, hits, index.volumes(hits)))
        else:
            missing.append(position)
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


def find_arc(
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
    if (current := find_arc(tags, name)) is None:
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
    *,
    variants: bool = False,
) -> tuple[ArcChange, ...]:
    """
    Plan the arc each found comic should carry, in path order.

    The arc is named ``name``; its number is the entry's place in an
    ordered list, the first place for an issue the list reads twice, in
    every copy of it. Only strict matches are planned, unless ``variants``,
    and never the comics of an entry that fits several volumes.
    """
    ordered = is_ordered(reading_list)
    numbers: dict[Path, int | None] = {}
    for found in result.found:
        if found.ambiguous:
            continue
        for comic in found.comics:
            if variants or comic.by.strict:
                numbers.setdefault(comic.path, found.position + 1 if ordered else None)
    return tuple(
        _change(path, _tags(comics[path]), name, numbers[path])
        for path in sorted(numbers)
    )


def _tags(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = metadata.get(ROOT_TAG)
    return inner if isinstance(inner, Mapping) else metadata
