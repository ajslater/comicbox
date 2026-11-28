"""
Match a reading list against the comics in a directory.

Each comic becomes an entry with ``entry_from_comic``. Matching goes in two
passes. First every entry takes each comic it shares a strict key with
(``entry_keys``: an issue id, the series name, start year or volume and
issue, or, weakest, the series name, cover year and issue). Then each entry
that found none tries its name variants in order, among the comics no entry
took strictly. Either way a comic is refused when it carries an id from a
database the entry has a different id from (a barcode excepted: it names a
cover or printing), or a cover year more than a year off the entry's.

The volume key and the cover-year key are loose: two volumes may share
either, and two issues may share the cover-year key. A comic that shares
only a loose key with an entry is refused when it is of another volume than
the entry, or has another id from one database than a strong match (by id or
start year); when one comic found has the entry's own signature, only such
loose comics are found, and otherwise one of another volume than a strong
match is refused; the loose comics left are ambiguous when any two are two
issues, of two volumes or with two ids from one database: listed, never
tagged. An entry with no key
matches nothing. A missing entry reports the comics refused that a person
may want to see (``Refused``). The matching is pure; reading the directory
is separate.
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
    BARCODE_ID_SOURCES,
    ID_KEY_KIND,
    NAME_KEY_KIND,
    NAME_YEAR_KEY_KIND,
    VOLUME_DISCRIMINATOR,
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

    ``ambiguous`` marks a loose match, on the volume or cover-year key,
    beside others of another issue, by volume or by id: ``match`` lists
    it, and does not choose between them.
    """

    path: Path
    by: FoundBy
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class Found:
    """
    The comics that are entry ``position`` (from 0), in path order.

    When some are ambiguous, ``volumes`` holds the discriminators they
    differ in, start years or volume numbers, and ``ids`` the ids they
    differ in, as ``(source, id)`` pairs; either may be empty.
    """

    position: int
    comics: tuple[FoundComic, ...]
    volumes: tuple[int, ...] = ()
    ids: tuple[tuple[str, str], ...] = ()

    @property
    def ambiguous(self) -> bool:
        """Whether some of the entry's comics are of issues it cannot tell apart."""
        return bool(self.volumes or self.ids)

    @property
    def paths(self) -> tuple[Path, ...]:
        """Get the paths of the comics found."""
        return tuple(comic.path for comic in self.comics)


class RefusedReason(StrEnum):
    """Why a comic that looked like a missing entry was refused."""

    # It shares the entry's series, issue and cover year, of another volume.
    OTHER_VOLUME = "other-volume"
    # It shares an id or a name key, and its cover year is more than a year off.
    COVER_YEAR = "cover-year"


@dataclass(frozen=True, slots=True)
class Refused:
    """A comic refused for missing entry ``position`` (from 0), and why."""

    position: int
    path: Path
    reason: RefusedReason


@dataclass(frozen=True, slots=True)
class MatchResult:
    """
    What a directory has of a list, and what it is missing, by position.

    ``refused`` holds, for missing entries only, the comics refused for
    another volume or cover year that no entry found, by position, then
    path.
    """

    found: tuple[Found, ...]
    missing: tuple[int, ...]
    refused: tuple[Refused, ...] = ()


def _year(entry: Mapping[str, Any]) -> int | None:
    """Get an entry's cover year; a date that did not parse has none."""
    when = entry_date(entry)
    return when.year if isinstance(when, date) else None


@dataclass(frozen=True, slots=True)
class _Facts:
    """
    What vetoes a match: an entry's or comic's issue ids and cover year.

    And its discriminators, which veto a match on the cover-year key alone.
    ``ids`` holds no barcode: one differing names another cover, printing or
    edition of the issue, so it vetoes nothing.
    """

    ids: Mapping[str, str]
    year: int | None
    discriminators: Discriminators

    @classmethod
    def of(cls, entry: Mapping[str, Any], keys: Sequence[EntryKey]) -> "_Facts":
        ids = {
            key[1]: key[2]
            for key in keys
            if key[0] == ID_KEY_KIND and key[1] not in BARCODE_ID_SOURCES
        }
        return cls(ids, _year(entry), discriminators(entry))

    def other_volume(self, other: "_Facts") -> bool:
        """Tell whether the two sides are of two volumes."""
        return self.discriminators.conflicts(other.discriminators)

    def ids_differ(self, other: "_Facts") -> bool:
        """Tell whether the sides have different ids from one database."""
        return any(
            other.ids.get(source, key) != key for source, key in self.ids.items()
        )

    def years_apart(self, other: "_Facts") -> bool:
        """Tell whether the sides' cover years are more than a year apart."""
        return (
            self.year is not None
            and other.year is not None
            and abs(self.year - other.year) > _COVER_YEAR_SLACK
        )

    def contradicts(self, other: "_Facts") -> bool:
        """Tell whether two sides cannot be one issue, whatever their keys."""
        return self.ids_differ(other) or self.years_apart(other)

    def refuses(self, other: "_Facts", key: EntryKey) -> bool:
        """
        Tell whether a match of the two sides on ``key`` is refused.

        Beyond ``contradicts``, a match on the volume key is refused for two
        years: Z-Men (1963) and Z-Men (1991) may both be volume 1.
        """
        return self.contradicts(other) or _volume_of_another_year(self, other, key)


def _volume_of_another_year(one: _Facts, other: _Facts, key: EntryKey) -> bool:
    """Tell whether a volume-key match is of two volumes, told by their years."""
    return (
        key[0] == NAME_KEY_KIND
        and key[2] == VOLUME_DISCRIMINATOR
        and one.other_volume(other)
    )


def _differing(values: Collection[Discriminators]) -> tuple[int, ...]:
    """Get the discriminators some rows differ in: years, volume numbers or both."""
    years = {value.year for value in values if value.year is not None}
    volumes = {value.volume for value in values if value.volume is not None}
    differing = (years if len(years) > 1 else set()) | (
        volumes if len(volumes) > 1 else set()
    )
    return tuple(sorted(differing))


def _differing_ids(facts: Collection[_Facts]) -> tuple[tuple[str, str], ...]:
    """Get the ids some rows differ in, from one database, as ``(source, id)``."""
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    for one in facts:
        for source, key in one.ids.items():
            by_source[source].add(key)
    return tuple(
        sorted(
            (source, key)
            for source, keys in by_source.items()
            if len(keys) > 1
            for key in keys
        )
    )


def _is_loose(key: EntryKey) -> bool:
    """
    Tell whether a key leaves a discriminator unsaid: the volume or cover-year key.

    The volume key says no start year, the cover-year key no start year and
    no volume, so two volumes may share either.
    """
    return key[0] == NAME_YEAR_KEY_KIND or (
        key[0] == NAME_KEY_KIND and key[2] == VOLUME_DISCRIMINATOR
    )


def _loose_found(
    paths: Collection[Path], by: Mapping[Path, FoundBy], *, ambiguous: bool
) -> list[FoundComic]:
    return [FoundComic(path, by[path], ambiguous=ambiguous) for path in paths]


def _refused_reason(
    entry: _Facts, comic: _Facts, key: EntryKey
) -> RefusedReason | None:
    """Say why a comic sharing ``key`` was refused, if a person may want it."""
    if entry.ids_differ(comic):
        return None
    if key[0] == NAME_YEAR_KEY_KIND:
        if not entry.years_apart(comic) and entry.other_volume(comic):
            return RefusedReason.OTHER_VOLUME
    elif (
        key[0] in {ID_KEY_KIND, NAME_KEY_KIND}
        and entry.years_apart(comic)
        and not _volume_of_another_year(entry, comic, key)
    ):
        return RefusedReason.COVER_YEAR
    return None


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

        Strong matches share an id or the year key, and are always found. A
        loose match shares only the volume key or the cover-year key, and is
        judged by ``_loose_matches``. None when nothing is found.
        """
        keys = entry_keys(entry)
        facts = _Facts.of(entry, keys)
        strong: dict[Path, FoundBy] = {}
        # The strongest key comes first, so a comic found by two is found by it.
        for key in keys:
            if _is_loose(key):
                continue
            by = FoundBy.ID if key[0] == ID_KEY_KIND else FoundBy.NAME
            for path in self.strict.get(key, ()):
                if path not in strong and not facts.refuses(self.facts[path], key):
                    strong[path] = by
        by_key = self._loose_candidates(keys, facts, strong)
        loose, unsure = self._loose_matches(facts, strong, by_key)
        comics = [
            *(FoundComic(path, by) for path, by in strong.items()),
            *_loose_found(loose, by_key, ambiguous=False),
            *_loose_found(unsure, by_key, ambiguous=True),
        ]
        if not comics:
            return None
        unsure_facts = [self.facts[path] for path in unsure]
        return Found(
            -1,
            tuple(sorted(comics, key=lambda comic: comic.path)),
            _differing([one.discriminators for one in unsure_facts]),
            _differing_ids(unsure_facts),
        )

    def _loose_matches(
        self,
        facts: "_Facts",
        strong: Collection[Path],
        candidates: Collection[Path],
    ) -> tuple[list[Path], list[Path]]:
        """
        Judge the comics that share only a loose key with an entry, together.

        Each ``candidate`` has passed the vetoes and is not of another volume
        than the entry (``Discriminators.conflicts``). One with another id
        from one database than a strong match is refused. When some comic
        found for the entry, by any key, has the entry's own signature, only
        such comics are kept: no looser one is. Otherwise one of another
        volume than any strong match is refused. The comics kept are judged
        together: if any two are two issues, of two volumes or with two ids
        from one database, they are all ambiguous. Returns the comics found
        and those ambiguous.
        """
        strong_facts = [self.facts[path] for path in strong]
        candidates = [
            path
            for path in candidates
            if not any(self.facts[path].ids_differ(one) for one in strong_facts)
        ]
        if (kept := self._exact_only(facts, strong, candidates)) is None:
            kept = [
                path
                for path in candidates
                if not any(self.facts[path].other_volume(one) for one in strong_facts)
            ]
        kept_facts = [self.facts[path] for path in kept]
        if any_conflict(one.discriminators for one in kept_facts) or _differing_ids(
            kept_facts
        ):
            return [], kept
        return kept, []

    def _exact_only(
        self, facts: "_Facts", strong: Collection[Path], candidates: Collection[Path]
    ) -> list[Path] | None:
        """
        Find the loose comics of the entry's own signature, when exact ones rule.

        When some comic found for the entry, by any key, has the entry's own
        signature, no looser comic is found: returns the exact loose ones.
        None when there is no exact comic, and the loose rules apply.
        """
        own = facts.discriminators
        if not any(
            self.facts[path].discriminators == own for path in (*strong, *candidates)
        ):
            return None
        return [path for path in candidates if self.facts[path].discriminators == own]

    def _loose_candidates(
        self,
        keys: Sequence[EntryKey],
        facts: "_Facts",
        strong: Collection[Path],
    ) -> dict[Path, FoundBy]:
        """
        List the comics sharing only a loose key, after the vetoes, and how.

        One sharing the volume key is found by name, one sharing only the
        cover-year key by name and year. Neither may conflict with the entry:
        a volume-key match is refused for another year, as Z-Men (1963) is
        for an Z-Men (1991) entry when both are volume 1.
        """
        candidates: dict[Path, FoundBy] = {}
        for key in filter(_is_loose, keys):
            by = FoundBy.NAME_YEAR if key[0] == NAME_YEAR_KEY_KIND else FoundBy.NAME
            for path in self.strict.get(key, ()):
                if (
                    path not in strong
                    and path not in candidates
                    and not facts.contradicts(self.facts[path])
                    and not facts.other_volume(self.facts[path])
                ):
                    candidates[path] = by
        return candidates

    def find_variant(
        self, entry: Mapping[str, Any], taken: Collection[Path]
    ) -> tuple[FoundComic, ...]:
        """Find an entry by its first name variant that some untaken comic has."""
        facts = _Facts.of(entry, entry_keys(entry))
        for key in variant_keys(entry):
            paths = [
                path
                for path in self.variants.get(key, ())
                if path not in taken and not facts.refuses(self.facts[path], key)
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

    def refused(self, entry: Mapping[str, Any], position: int) -> list[Refused]:
        """
        List the comics refused for a missing entry that a person may want.

        One sharing the cover-year key refused only as another volume, and
        one sharing an id or a name key refused only for its cover year. Not one of
        the same number in another volume and year: every missing issue of a
        long-running title would have those.
        """
        keys = entry_keys(entry)
        facts = _Facts.of(entry, keys)
        reasons: dict[Path, RefusedReason] = {}
        for key in keys:
            for path in self.strict.get(key, ()):
                if reason := _refused_reason(facts, self.facts[path], key):
                    reasons.setdefault(path, reason)
        return [Refused(position, path, reasons[path]) for path in sorted(reasons)]


def match_comics(
    reading_list: Mapping[str, Any], comics: Mapping[Path, Mapping[str, Any]]
) -> MatchResult:
    """
    Find each of a list's entries among some comics' tags.

    ``comics`` maps each comic's path to its tags, as a ``ReadResult``
    holds them. Strict matches are settled for the whole list first, so a
    comic one entry is strictly is never another entry's variant. A comic
    of one issue in several files is found in all, and an issue the list
    holds twice is found in the same comics both times. A loose match, on
    the volume or cover-year key, is refused beside strong matches of
    another volume, and is ambiguous beside loose matches of another
    volume; see ``_Index``. Each
    missing entry reports the comics ``_Index.refused`` finds for it that
    no entry found.
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
    refused = _refusals(index, entries, missing, found)
    return MatchResult(tuple(found), tuple(missing), refused)


def _refusals(
    index: _Index,
    entries: Sequence[Mapping[str, Any]],
    missing: Sequence[int],
    found: Sequence[Found],
) -> tuple[Refused, ...]:
    """List the missing entries' refused comics that no entry found."""
    claimed = frozenset(path for one in found for path in one.paths)
    return tuple(
        refusal
        for position in missing
        for refusal in index.refused(entries[position], position)
        if refusal.path not in claimed
    )


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
