"""
Combining and matching randomized lists: the invariants that hold whatever the input.

Each is worked out from the generated fields, never by asking the code under
test what it thinks: every row lands once, no entry holds two rows of one
list, the first list's order is kept, a keyed list combines with itself
unchanged, compare is symmetric, no group holds two volumes, and permuting a
list that repeats no issue changes no group, and a bare row that another
list leaves between two volumes joins none of that list's rows of a volume.
Matching a list against comics never tags two volumes for one entry, nor
two loose comics with differing ids, and a comic is always found by the
entry made from its own tags: taggable, unless it has no id from a database
in which two comics it fits differ.
"""

import random
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    Verdict,
    combine,
    compare,
)
from comicbox.readinglists.match import FoundBy, match_comics, plan_arcs
from comicbox.readinglists.serialize import load_model


def _entry(
    number: int,
    *,
    series: str = "Crimson Tide",
    year: int | None = 2006,
    cover: date | None = None,
    **ids: str,
) -> dict[str, Any]:
    """Build an entry; with no year it has no name key and joins by id only."""
    entry_series: dict[str, Any] = {"name": series}
    if year is not None:
        entry_series["start_year"] = year
    entry: dict[str, Any] = {"series": entry_series, "issue": {"name": str(number)}}
    if cover is not None:
        entry["date"] = {"cover_date": cover}
    if ids:
        entry["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return entry


def _list(entries: list[dict[str, Any]], **header: Any) -> dict[str, Any]:
    return {"name": "Crimson Tide", "ordered": True, ENTRIES_KEY: entries, **header}


@dataclass(frozen=True, slots=True)
class _Issue:
    series: str
    number: int
    year: int
    comicvine: str
    metron: str
    # A volume number. Such an issue's row has its start year (``year``),
    # its volume number, both or neither.
    volume: int | None = None


# Every row of a numbered volume carries this cover date: two volumes' rows
# share the cover-year key, and only their discriminators tell them apart.
_VOLUME_COVER = date(2015, 1, 1)
_VOLUME_FORMS = ("both", "year", "volume", "neither")
# How often a volume's row carries each id: in the whole pool, and densely.
_VOLUME_ID_ODDS = 0.25
_DENSE_ID_ODDS = 0.7
# Many short lists: small groups over disjoint lists, which only the group
# guard keeps apart when an exact pair of rows with no year would join them.
_DENSE_LISTS = (8, 10)
_DENSE_ROWS = (1, 2)
# How often a row is repeated as it is, beside the repeats drawn afresh.
_IDENTICAL_ODDS = 0.1
# One seed in four: a few lists of one issue in three volumes, often
# repeating a row as it is, its rows seldom with ids.
_REPEATING_SEEDS = 3
_REPEATING_LISTS = (2, 3)
_REPEATING_ROWS = (2, 3)
_REPEATING_ID_ODDS = 0.2
_REPEATING_IDENTICAL_ODDS = 0.5
# The invariant tests run over this many seeds: even ones draw from the whole
# pool, odd ones densely from a few issues in two volumes (``_dense_inputs``).
SEEDS = range(80)


# Each volume: its number and start year. A relaunch numbered volume 1 again
# shares the volume key with the first: only their start years differ.
_VOLUMES = ((1, 1999), (2, 2014), (1, 2020))


def _volume_issues(numbers: range) -> list[_Issue]:
    """Issues in volumes 1 and 2 and a relaunched 1, with one cover year."""
    return [
        _Issue(
            f"Series {number % 4}",
            number,
            year,
            f"cv{number}v{index}",
            f"m{number}v{index}",
            volume,
        )
        for number in numbers
        for index, (volume, year) in enumerate(_VOLUMES)
    ]


def _random_inputs(seed: int) -> list[dict[str, Any]]:
    """
    Build lists of one pool of issues with consistent ids, some dropped.

    Every third issue has a twin with the same series, year and number and
    ids of its own, as a reprint has: rows a name key cannot tell apart.
    Some issues come in volumes 1 and 2, with one cover year: their rows
    have a start year and a volume number, one of them, or neither. An odd
    seed draws its lists from those alone, densely, and one in four from
    one issue in three volumes, repeating rows.
    """
    rng = random.Random(seed)  # noqa: S311 - a test fixture, not a secret
    if seed % 4 == _REPEATING_SEEDS:
        return _repeating_inputs(rng)
    if seed % 2:
        return _dense_inputs(rng)
    pool = [
        _Issue(
            f"Series {number % 4}",
            number // 2 if number % 3 == 0 else number,
            2000 + number % 3,
            f"cv{number}",
            f"m{number}",
        )
        for number in range(24)
    ]
    pool.extend(
        replace(issue, comicvine=f"{issue.comicvine}t", metron=f"{issue.metron}t")
        for issue in pool[::3]
    )
    pool.extend(_volume_issues(range(30, 42)))
    return _lists(rng, pool, rng.randint(2, 4), (6, 18), _VOLUME_ID_ODDS)


def _dense_inputs(rng: random.Random) -> list[dict[str, Any]]:
    """
    Build eight to ten short lists from two issues in volumes 1 and 2.

    Two volumes of one issue meet often, and ids tie a row with no year to a
    row of its volume often enough that only the group guard keeps two such
    groups apart.
    """
    issues = _volume_issues(range(30, 32))
    return _lists(rng, issues, rng.randint(*_DENSE_LISTS), _DENSE_ROWS, _DENSE_ID_ODDS)


def _repeating_inputs(rng: random.Random) -> list[dict[str, Any]]:
    """
    Build two or three short lists of one issue in three volumes, with repeats.

    A list reads a row with no year twice beside another list's rows of two
    volumes, some of them twice: occurrences counted by signature split the
    other list's rows, and only counting all of them keeps the row apart.
    """
    issues = _volume_issues(range(30, 31))
    return _lists(
        rng,
        issues,
        rng.randint(*_REPEATING_LISTS),
        _REPEATING_ROWS,
        _REPEATING_ID_ODDS,
        _REPEATING_IDENTICAL_ODDS,
    )


def _lists(
    rng: random.Random,
    pool: list[_Issue],
    count: int,
    size: tuple[int, int],
    odds: float,
    identical: float = _IDENTICAL_ODDS,
) -> list[dict[str, Any]]:
    inputs = []
    for _ in range(count):
        rows = []
        for issue in rng.sample(pool, rng.randint(*size)):
            rows.append(_random_row(rng, issue, odds))
            if rng.random() < 0.15:
                # The issue again, with its ids drawn afresh: B=[X{gcd},
                # X{cv}] beside A=[X{cv, gcd}] leaves one id on two entries.
                rows.append(_random_row(rng, issue, odds))
            elif rng.random() < identical:
                # The same row again, as a list that reads an issue twice.
                rows.append(dict(rows[-1]))
        inputs.append(_list(rows))
    return inputs


def _random_row(rng: random.Random, issue: _Issue, odds: float) -> dict[str, Any]:
    """Write one issue as a list might: some ids, maybe no year."""
    year = issue.year if rng.random() < 0.7 else None
    if issue.volume is None:
        row = _entry(issue.number, series=issue.series, year=year)
    else:
        form = rng.choice(_VOLUME_FORMS)
        row = _entry(
            issue.number,
            series=issue.series,
            year=issue.year if form in {"both", "year"} else None,
            cover=_VOLUME_COVER,
        )
        if form in {"both", "volume"}:
            row["volume"] = {"number": issue.volume}
    ids = (("comicvine", issue.comicvine), ("metron", issue.metron))
    # A volume's rows carry fewer ids, so more of them join by cover year.
    odds = 0.6 if issue.volume is None else odds
    if identifiers := {
        source: {"key": key} for source, key in ids if rng.random() < odds
    }:
        row["identifiers"] = identifiers
    return row


def _id_counts(entries: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(
        (source, identifier["key"])
        for entry in entries
        for source, identifier in (entry.get("identifiers") or {}).items()
    )


def _repeated_ids(inputs: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Get each id that an input puts on two of its own rows."""
    return {
        id_key
        for reading_list in inputs
        for id_key, count in _id_counts(reading_list[ENTRIES_KEY]).items()
        if count > 1
    }


@pytest.mark.parametrize("seed", SEEDS)
def test_no_id_lands_on_two_entries_unreported(seed: int) -> None:
    """An id on two entries is repeated by an input, or reported as shared."""
    inputs = _random_inputs(seed)
    result = combine(inputs)
    repeated = _repeated_ids(inputs)
    shared = {(item.source, item.key) for item in result.shared_ids}
    for id_key, count in _id_counts(result.reading_list[ENTRIES_KEY]).items():
        assert count == 1 or id_key in repeated or id_key in shared, id_key
    for members in result.provenance:
        assert len({origin.input_index for origin in members}) == len(members)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_shared_id_reported_is_on_two_entries_and_repeated_by_none(
    seed: int,
) -> None:
    """Each is on every entry it names, and no input puts it on two rows."""
    inputs = _random_inputs(seed)
    result = combine(inputs)
    repeated = _repeated_ids(inputs)
    shared = {(item.source, item.key): item.entries for item in result.shared_ids}
    entries = result.reading_list[ENTRIES_KEY]
    for (source, key), positions in shared.items():
        assert (source, key) not in repeated
        assert len(positions) > 1
        for position in positions:
            assert entries[position]["identifiers"][source]["key"] == key


def _rows(result: Any, moves: list[list[int]] | None = None) -> set[frozenset]:
    """List each combined entry's rows, as rows before ``moves``, if given."""
    return {
        frozenset(
            (
                origin.input_index,
                moves[origin.input_index][origin.row] if moves else origin.row,
            )
            for origin in origins
        )
        for origins in result.provenance
    }


def _signature(entry: dict[str, Any]) -> tuple[Any, Any]:
    """Get a generated row's start year and volume number."""
    return entry["series"].get("start_year"), (entry.get("volume") or {}).get("number")


def _conflict(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Tell whether two generated rows differ in a start year or a volume number."""
    return any(
        mine is not None and theirs is not None and mine != theirs
        for mine, theirs in zip(_signature(one), _signature(other), strict=True)
    )


def _same_issue_keys(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Tell whether two generated rows share an id, or a series and number."""
    ids = {(s, i["key"]) for s, i in (one.get("identifiers") or {}).items()}
    theirs = {(s, i["key"]) for s, i in (other.get("identifiers") or {}).items()}
    named = one["series"]["name"] == other["series"]["name"] and (
        one["issue"]["name"] == other["issue"]["name"]
    )
    return bool(ids & theirs) or named


def _without_repeats(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Drop each row that repeats an earlier one: same issue, and no conflict.

    What is left has no repeated issue: rows of one issue are of two
    volumes.
    """
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if not any(
            _same_issue_keys(entry, other) and not _conflict(entry, other)
            for other in kept
        ):
            kept.append(entry)
    return kept


def _two_volumes(inputs: list[dict[str, Any]], members: frozenset) -> bool:
    """
    Tell whether a group holds rows that say they are of two volumes.

    Worked out here from the generated fields, not by ``discriminators``: two
    start years, or two volume numbers, that differ. A start year and a
    volume number cannot be compared, and may join.
    """
    rows = [inputs[index][ENTRIES_KEY][row] for index, row in members]
    years = {row["series"].get("start_year") for row in rows} - {None}
    volumes = {(row.get("volume") or {}).get("number") for row in rows} - {None}
    return len(years) > 1 or len(volumes) > 1


def _has_key(entry: dict[str, Any]) -> bool:
    """Tell whether a generated row has an entry key: an id, or a year to name it."""
    return bool(
        entry.get("identifiers")
        or entry["series"].get("start_year")
        or entry.get("volume")
        or entry.get("date")
    )


def _origins(result: Any) -> list[set[tuple[int, int]]]:
    return [
        {(origin.input_index, origin.row) for origin in o} for o in result.provenance
    ]


@pytest.mark.parametrize("seed", SEEDS)
def test_a_keyed_list_combines_with_itself_unchanged(seed: int) -> None:
    """Each row joins its own copy, and nothing else, so compare says same."""
    for generated in _random_inputs(seed):
        rows = [entry for entry in generated[ENTRIES_KEY] if _has_key(entry)]
        reading_list = {**generated, ENTRIES_KEY: rows}

        result = combine([reading_list, reading_list])

        assert result.reading_list[ENTRIES_KEY] == load_model(reading_list)[ENTRIES_KEY]
        assert _origins(result) == [{(0, row), (1, row)} for row in range(len(rows))]
        assert compare(reading_list, reading_list).verdict is Verdict.SAME


@pytest.mark.parametrize("seed", SEEDS)
def test_compare_is_the_same_both_ways_round(seed: int) -> None:
    one, other = _random_inputs(seed)[:2]
    forward, back = compare(one, other), compare(other, one)
    assert (forward.verdict, forward.overlap) == (back.verdict, back.overlap)


def _all_rows(inputs: list[dict[str, Any]]) -> set[tuple[int, int]]:
    return {
        (index, row)
        for index, rl in enumerate(inputs)
        for row in range(len(rl[ENTRIES_KEY]))
    }


@pytest.mark.parametrize("seed", SEEDS)
def test_every_row_lands_once_in_the_first_lists_order(seed: int) -> None:
    """In one entry each, never two of one list together, the first list in order."""
    inputs = _random_inputs(seed)

    result = combine(inputs)

    entries = _origins(result)
    landed = Counter(node for members in entries for node in members)
    assert landed == Counter(_all_rows(inputs))
    assert all(
        len({index for index, _ in members}) == len(members) for members in entries
    )
    first = [row for members in entries for index, row in sorted(members) if index == 0]
    assert first == sorted(first)
    again = combine(inputs)
    assert (again.reading_list, again.provenance) == (
        result.reading_list,
        result.provenance,
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_no_group_holds_rows_of_two_volumes(seed: int) -> None:
    """
    Two start years, or two volume numbers, never meet in one entry.

    An id could join two volumes' rows, but the generator's ids are each
    volume's own, so any such entry was made by the cover-year key.
    """
    inputs = _random_inputs(seed)
    assert not any(_two_volumes(inputs, members) for members in _rows(combine(inputs)))


@pytest.mark.parametrize("seed", SEEDS)
def test_the_grouping_survives_permuting_an_inputs_rows(seed: int) -> None:
    """Permuting the rows of a list that repeats no issue changes no group."""
    rng = random.Random(seed)  # noqa: S311 - a test fixture, not a secret
    inputs = [
        {**rl, ENTRIES_KEY: _without_repeats(rl[ENTRIES_KEY])}
        for rl in _random_inputs(seed)
    ]
    moves = [
        rng.sample(range(len(rl[ENTRIES_KEY])), len(rl[ENTRIES_KEY])) for rl in inputs
    ]
    permuted = [
        {**rl, ENTRIES_KEY: [rl[ENTRIES_KEY][row] for row in order]}
        for rl, order in zip(inputs, moves, strict=True)
    ]

    assert _rows(combine(permuted), moves) == _rows(combine(inputs))


def _bare(entry: dict[str, Any]) -> bool:
    """Tell whether a generated row has only its cover year: no id, start year or volume."""
    return bool(
        entry.get("date")
        and not entry.get("identifiers")
        and _signature(entry) == (None, None)
    )


def _cover_mates(
    entry: dict[str, Any], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """List the rows sharing a row's series, issue and cover date: its cover-year key."""
    return [
        other
        for other in entries
        if other.get("date")
        and other.get("date") == entry.get("date")
        and other["series"]["name"] == entry["series"]["name"]
        and other["issue"]["name"] == entry["issue"]["name"]
    ]


def _of_two_volumes(rows: list[dict[str, Any]]) -> bool:
    years = {row["series"].get("start_year") for row in rows} - {None}
    volumes = {(row.get("volume") or {}).get("number") for row in rows} - {None}
    return len(years) > 1 or len(volumes) > 1


@pytest.mark.parametrize("seed", SEEDS)
def test_a_bare_row_another_list_leaves_between_two_volumes_joins_neither(
    seed: int,
) -> None:
    """
    Combining two lists, such a row never joins a row of a volume.

    A bare row of the first list whose cover-year key rows of two volumes in
    the second share, whichever time each comes in that list, has only that
    key, so nothing else could join it: it joins a bare row there or none.
    """
    inputs = _random_inputs(seed)
    for one, other in ((0, 1), (1, 0)):
        lists = [inputs[one], inputs[other]]
        result = combine(lists)
        rows, theirs = lists[0][ENTRIES_KEY], lists[1][ENTRIES_KEY]
        for members in _rows(result):
            mine = [row for index, row in members if index == 0]
            if not mine or not _bare(rows[mine[0]]):
                continue
            if not _of_two_volumes(_cover_mates(rows[mine[0]], theirs)):
                continue
            joined = [theirs[row] for index, row in members if index == 1]
            assert all(_signature(row) == (None, None) for row in joined), (
                one,
                mine[0],
            )


def _forms(entries: list[dict[str, Any]]) -> set[tuple[bool, bool]]:
    """Name which discriminators the dated rows carry: start year, volume, both, none."""
    return {
        (entry["series"].get("start_year") is not None, entry.get("volume") is not None)
        for entry in entries
        if entry.get("date")
    }


def test_the_generator_draws_every_form_in_one_list_and_rows_that_conflict() -> None:
    """The invariants are only worth having if the inputs can break them."""
    every_form = {(True, True), (True, False), (False, True), (False, False)}
    assert any(
        _forms(rl[ENTRIES_KEY]) == every_form
        for seed in SEEDS
        for rl in _random_inputs(seed)
    )
    assert any(
        _conflict(kept[one], kept[other]) and _same_issue_keys(kept[one], kept[other])
        for seed in SEEDS
        for rl in _random_inputs(seed)
        for kept in [_without_repeats(rl[ENTRIES_KEY])]
        for one in range(len(kept))
        for other in range(one)
    )


def test_the_generator_repeats_a_bare_row_beside_two_volumes() -> None:
    """The bare-row invariant needs a list reading such a row twice."""
    assert any(
        rows.count(row) > 1 and _of_two_volumes(_cover_mates(row, other[ENTRIES_KEY]))
        for seed in SEEDS
        for inputs in [_random_inputs(seed)]
        for rows, other in (
            (inputs[0][ENTRIES_KEY], inputs[1]),
            (inputs[1][ENTRIES_KEY], inputs[0]),
        )
        for row in rows
        if _bare(row)
    )


def test_the_generator_makes_shared_ids() -> None:
    """The restated test is only worth having if some seed shares an id."""
    assert any(combine(_random_inputs(seed)).shared_ids for seed in SEEDS)


# ------------------------------------------------------------------ matching


def _comics(entries: list[dict[str, Any]]) -> dict[Path, dict[str, Any]]:
    """Make each generated row a comic, its tags the row."""
    return {Path(f"{row:03}.cbz"): entry for row, entry in enumerate(entries)}


@pytest.mark.parametrize("seed", SEEDS)
def test_matching_never_tags_two_volumes_for_one_entry(seed: int) -> None:
    """
    The comics planned for one entry never hold two start years or volumes.

    The generator's ids are each volume's own, so two volumes planned for
    one entry were found by a name key that could not tell them apart.
    """
    inputs = _random_inputs(seed)
    for reading_list in inputs:
        # The library: every other list's rows.
        comics = _comics(
            [
                row
                for other in inputs
                if other is not reading_list
                for row in other[ENTRIES_KEY]
            ]
        )
        result = match_comics(reading_list, comics)
        for found in result.found:
            taggable = {
                comic.path
                for comic in found.comics
                if comic.by.strict and not comic.ambiguous
            }
            rows = [comics[path] for path in taggable]
            years = {row["series"].get("start_year") for row in rows} - {None}
            volumes = {(row.get("volume") or {}).get("number") for row in rows} - {None}
            assert len(years) <= 1, (found.position, sorted(taggable))
            assert len(volumes) <= 1, (found.position, sorted(taggable))
        planned = {
            change.path for change in plan_arcs(reading_list, comics, result, "A")
        }
        assert planned <= {
            comic.path for found in result.found for comic in found.comics
        }


def _ids(entry: dict[str, Any]) -> dict[str, str]:
    return {
        source: identifier["key"]
        for source, identifier in (entry.get("identifiers") or {}).items()
    }


def _ids_differ(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Tell whether two generated rows have two ids from one database."""
    theirs = _ids(other)
    return any(theirs.get(source, key) != key for source, key in _ids(one).items())


def _loose(entry: dict[str, Any], row: dict[str, Any], by: FoundBy) -> bool:
    """
    Tell whether a comic was found by a loose key: the cover year or the volume.

    The generator's volume numbers are all under 1900, so a name match is by
    the year key only when both sides have a start year.
    """
    return by is FoundBy.NAME_YEAR or (
        by is FoundBy.NAME
        and None in {entry["series"].get("start_year"), row["series"].get("start_year")}
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_matching_never_tags_two_issues_by_id_on_a_loose_key(seed: int) -> None:
    """
    No two comics planned for an entry, one of them loose, have two ids.

    From one database: two loose comics, or a loose comic and a strong one.
    Two strong matches, by id or the year key, are not judged by each other.
    """
    inputs = _random_inputs(seed)
    for reading_list in inputs:
        comics = _comics(
            [
                row
                for other in inputs
                if other is not reading_list
                for row in other[ENTRIES_KEY]
            ]
        )
        result = match_comics(reading_list, comics)
        for found in result.found:
            entry = reading_list[ENTRIES_KEY][found.position]
            planned = [
                (comics[comic.path], _loose(entry, comics[comic.path], comic.by))
                for comic in found.comics
                if comic.by.strict and not comic.ambiguous
            ]
            assert not any(
                _ids_differ(row, other)
                for (row, loose), (other, other_loose) in combinations(planned, 2)
                if loose or other_loose
            ), found.position


@pytest.mark.parametrize("seed", SEEDS)
def test_a_comic_is_found_by_the_entry_made_from_its_own_tags(seed: int) -> None:
    """
    A thing compared with itself: found, and ambiguous only by an id it lacks.

    A comic with no id from a database, beside two comics it fits that have
    two ids from it, cannot tell which of them it is.
    """
    for generated in _random_inputs(seed):
        rows = [entry for entry in generated[ENTRIES_KEY] if _has_key(entry)]
        comics = _comics(rows)
        result = match_comics({**generated, ENTRIES_KEY: rows}, comics)
        found = {one.position: one for one in result.found}
        for position, path in enumerate(comics):
            assert position in found, position
            own = [comic for comic in found[position].comics if comic.path == path]
            assert own, position
            if not own[0].ambiguous:
                continue
            fits = [comics[c.path] for c in found[position].comics if c.ambiguous]
            assert not _of_two_volumes(fits), position
            lacking = {
                source
                for row in fits
                for source in _ids(row)
                if source not in _ids(rows[position])
                and len({_ids(one).get(source) for one in fits} - {None}) > 1
            }
            assert lacking, position


def test_the_generator_gives_loose_comics_differing_ids() -> None:
    """The id invariants are only worth having if two bare rows differ by id."""
    assert any(
        _ids_differ(row, mate)
        for seed in SEEDS
        for rl in _random_inputs(seed)
        for row in rl[ENTRIES_KEY]
        if _signature(row) == (None, None) and row.get("date")
        for mate in _cover_mates(row, rl[ENTRIES_KEY])
        if _signature(mate) == (None, None)
    )


def test_the_generator_gives_one_volume_number_two_start_years() -> None:
    """The volume key meets two years only if some list draws both."""
    assert any(
        len(
            {
                entry["series"].get("start_year")
                for entry in rl[ENTRIES_KEY]
                if (entry.get("volume") or {}).get("number") == 1
            }
            - {None}
        )
        > 1
        for seed in SEEDS
        for rl in _random_inputs(seed)
    )
