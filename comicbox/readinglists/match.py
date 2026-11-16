"""
Match a reading list against the comics in a directory.

Each comic becomes an entry with ``entry_from_comic``. Matching goes in two
passes. First every entry takes each comic it shares a strict key with
(``entry_keys``: an issue id, the series name, start year or volume and
issue, or, weakest, the series name, cover year and issue). Then each entry that found none tries its name variants in order,
among the comics no entry took strictly. Either way a comic is refused when
it carries an id from a database the entry has a different id from, or a
cover year more than a year off the entry's. A comic that shares only the
cover-year key is refused for another series year than the entry's or its
strong matches', and is ambiguous beside cover-year matches of another
volume: listed, never tagged. An entry with no key matches
nothing. The matching is pure; reading the directory is separate.
"""

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
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
    NAME_YEAR_KEY_KIND,
    Discriminators,
    EntryKey,
    any_conflict,
    discriminators,
    entry_date,
    entry_keys,
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


@dataclass(frozen=True, slots=True)
class FoundComic:
    """
    One comic an entry was found in, and how.

    ``ambiguous`` marks a cover-year match beside others of another
    volume: ``match`` lists it, and does not choose between them.
    """

    path: Path
    by: FoundBy
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class Found:
    """
    The comics that are entry ``position`` (from 0), in path order.

    ``volumes`` holds the discriminators its ambiguous cover-year matches
    carry, start years or volume numbers, when it has any.
    """

    position: int
    comics: tuple[FoundComic, ...]
    volumes: tuple[int, ...] = ()

    @property
    def ambiguous(self) -> bool:
        """Whether some of the entry's comics are of volumes it cannot tell apart."""
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

    And its discriminators, which veto a match on the cover-year key alone.
    """

    ids: Mapping[str, str]
    year: int | None
    discriminators: Discriminators

    @classmethod
    def of(cls, entry: Mapping[str, Any], keys: Sequence[EntryKey]) -> "_Facts":
        ids = {key[1]: key[2] for key in keys if key[0] == ID_KEY_KIND}
        return cls(ids, _year(entry), discriminators(entry))

    def other_volume(self, other: "_Facts") -> bool:
        """Tell whether the two sides are of two volumes."""
        return self.discriminators.conflicts(other.discriminators)

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


def _differing(values: Collection[Discriminators]) -> tuple[int, ...]:
    """Get the discriminators some rows differ in: years, volume numbers or both."""
    years = {value.year for value in values if value.year is not None}
    volumes = {value.volume for value in values if value.volume is not None}
    differing = (years if len(years) > 1 else set()) | (
        volumes if len(volumes) > 1 else set()
    )
    return tuple(sorted(differing))


def _cover_year_found(paths: Collection[Path], *, ambiguous: bool) -> list[FoundComic]:
    return [FoundComic(path, FoundBy.NAME_YEAR, ambiguous=ambiguous) for path in paths]


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

    def find_strict(self, entry: Mapping[str, Any]) -> Found | None:
        """
        Find the comics that share a strict key with an entry, at position -1.

        Strong matches share an id or a name key, and are always found. A
        cover-year match shares only the cover-year key, and is judged by
        ``_cover_year_matches``. None when nothing is found.
        """
        keys = entry_keys(entry)
        facts = _Facts.of(entry, keys)
        strong: dict[Path, FoundBy] = {}
        # The strongest key comes first, so a comic found by two is found by it.
        for key in keys:
            if key[0] == NAME_YEAR_KEY_KIND:
                continue
            by = FoundBy.ID if key[0] == ID_KEY_KIND else FoundBy.NAME
            for path in self.strict.get(key, ()):
                if path not in strong and not facts.contradicts(self.facts[path]):
                    strong[path] = by
        cover, unsure, volumes = self._cover_year_matches(keys, facts, strong)
        comics = [
            *(FoundComic(path, by) for path, by in strong.items()),
            *_cover_year_found(cover, ambiguous=False),
            *_cover_year_found(unsure, ambiguous=True),
        ]
        if not comics:
            return None
        return Found(-1, tuple(sorted(comics, key=lambda comic: comic.path)), volumes)

    def _cover_year_matches(
        self,
        keys: Sequence[EntryKey],
        facts: "_Facts",
        strong: Collection[Path],
    ) -> tuple[list[Path], list[Path], tuple[int, ...]]:
        """
        Judge the comics that share only an entry's cover-year key.

        Each is refused when it conflicts with the entry
        (``Discriminators.conflicts``). One that shares a kind of
        discriminator with some strong match is found if it agrees with one
        of those, and refused if not. The rest are judged together: if any
        two conflict, they are all ambiguous. Returns the comics found, those
        ambiguous, and the discriminators they differ in.
        """
        strong_values = [self.facts[path].discriminators for path in strong]
        found: list[Path] = []
        rest: list[Path] = []
        for path in self._cover_year_candidates(keys, facts, strong):
            value = self.facts[path].discriminators
            peers = [other for other in strong_values if value.shares_a_kind(other)]
            if not peers:
                rest.append(path)
            elif any(not value.conflicts(other) for other in peers):
                found.append(path)
        rest_values = [self.facts[path].discriminators for path in rest]
        if any_conflict(rest_values):
            return found, rest, _differing(rest_values)
        return found + rest, [], ()

    def _cover_year_candidates(
        self,
        keys: Sequence[EntryKey],
        facts: "_Facts",
        strong: Collection[Path],
    ) -> list[Path]:
        """List the comics sharing only the cover-year key, after the vetoes."""
        key = next((key for key in keys if key[0] == NAME_YEAR_KEY_KIND), None)
        return [
            path
            for path in (self.strict.get(key, ()) if key else ())
            if path not in strong
            and not facts.contradicts(self.facts[path])
            and not facts.other_volume(self.facts[path])
        ]

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
    holds twice is found in the same comics both times. A cover-year match
    is refused beside strong matches of another volume, and is ambiguous
    beside cover-year matches of another volume; see ``_Index``.
    """
    index = _Index(comics)
    entries = tuple(reading_list.get(ENTRIES_KEY) or ())
    strict = [index.find_strict(entry) for entry in entries]
    taken = frozenset(path for found in strict if found for path in found.paths)
    found: list[Found] = []
    missing: list[int] = []
    for position, (entry, strong) in enumerate(zip(entries, strict, strict=True)):
        if strong is not None:
            found.append(replace(strong, position=position))
        elif variants := index.find_variant(entry, taken):
            found.append(Found(position, variants))
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
    and never an ambiguous one.
    """
    ordered = is_ordered(reading_list)
    numbers: dict[Path, int | None] = {}
    for found in result.found:
        for comic in found.comics:
            if (variants or comic.by.strict) and not comic.ambiguous:
                numbers.setdefault(comic.path, found.position + 1 if ordered else None)
    return tuple(
        _change(path, _tags(comics[path]), name, numbers[path])
        for path in sorted(numbers)
    )


def _tags(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = metadata.get(ROOT_TAG)
    return inner if isinstance(inner, Mapping) else metadata
