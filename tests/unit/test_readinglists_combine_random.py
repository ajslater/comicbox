"""
Combining randomized lists: the invariants that hold whatever the input.

Each is worked out from the generated fields, never by asking the code under
test what it thinks: every row lands once, no entry holds two rows of one
list, the first list's order is kept, a keyed list combines with itself
unchanged, compare is symmetric, no group holds two volumes, and permuting a
list that repeats no issue changes no group.
"""

import random
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    Verdict,
    combine,
    compare,
)
from comicbox.readinglists.serialize import load_model


def _entry(
    number: int,
    *,
    series: str = "Civil War",
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
    return {"name": "Civil War", "ordered": True, ENTRIES_KEY: entries, **header}


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
# The invariant tests run over this many seeds: even ones draw from the whole
# pool, odd ones densely from a few issues in two volumes (``_dense_inputs``).
SEEDS = range(80)


def _volume_issues(numbers: range) -> list[_Issue]:
    """Issues in volumes 1 and 2, started in 1999 and 2014, with one cover year."""
    return [
        _Issue(
            f"Series {number % 4}",
            number,
            1999 if v == 1 else 2014,
            f"cv{number}v{v}",
            f"m{number}v{v}",
            v,
        )
        for number in numbers
        for v in (1, 2)
    ]


def _random_inputs(seed: int) -> list[dict[str, Any]]:
    """
    Build lists of one pool of issues with consistent ids, some dropped.

    Every third issue has a twin with the same series, year and number and
    ids of its own, as a reprint has: rows a name key cannot tell apart.
    Some issues come in volumes 1 and 2, with one cover year: their rows
    have a start year and a volume number, one of them, or neither. An odd
    seed draws its lists from those alone, densely.
    """
    rng = random.Random(seed)  # noqa: S311 - a test fixture, not a secret
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


def _lists(
    rng: random.Random,
    pool: list[_Issue],
    count: int,
    size: tuple[int, int],
    odds: float,
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


@pytest.mark.parametrize("seed", SEEDS)
def test_no_id_lands_on_two_entries_unreported(seed: int) -> None:
    """
    An id on two entries is repeated by an input, or reported as shared.

    And every shared id reported is on two entries and repeated by none.
    """
    inputs = _random_inputs(seed)
    result = combine(inputs)
    repeated = {
        id_key
        for reading_list in inputs
        for id_key, count in _id_counts(reading_list[ENTRIES_KEY]).items()
        if count > 1
    }
    shared = {(item.source, item.key): item.entries for item in result.shared_ids}
    entries = result.reading_list[ENTRIES_KEY]
    for id_key, count in _id_counts(entries).items():
        assert count == 1 or id_key in repeated or id_key in shared, id_key
    for id_key, positions in shared.items():
        assert id_key not in repeated
        assert len(positions) > 1
        source, key = id_key
        for position in positions:
            assert entries[position]["identifiers"][source]["key"] == key
    for members in result.provenance:
        assert len({origin.input_index for origin in members}) == len(members)


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


def test_the_generator_makes_shared_ids() -> None:
    """The restated test is only worth having if some seed shares an id."""
    assert any(combine(_random_inputs(seed)).shared_ids for seed in SEEDS)
