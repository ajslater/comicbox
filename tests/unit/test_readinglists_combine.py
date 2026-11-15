"""Combining reading lists: identity, order, fields and the report."""

import random
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    EntryOrigin,
    IdConflict,
    OrderConflict,
    ReadingListError,
    combine,
    load,
)
from comicbox.readinglists.serialize import load_model
from tests.const import TEST_FILES_DIR

CIVIL_WAR_PATH = TEST_FILES_DIR / "readinglists" / "civil-war.yaml"


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


def _issues(reading_list: dict[str, Any]) -> list[str]:
    return [entry["issue"]["name"] for entry in reading_list[ENTRIES_KEY]]


def _numbers(*numbers: int, **kwargs: Any) -> list[dict[str, Any]]:
    return [_entry(number, **kwargs) for number in numbers]


def test_nothing_to_combine() -> None:
    with pytest.raises(ReadingListError):
        combine([])


def test_a_list_with_itself_is_unchanged() -> None:
    reading_list = load(CIVIL_WAR_PATH).reading_list
    assert combine([reading_list]).reading_list == reading_list
    result = combine([reading_list, reading_list])
    assert result.reading_list == reading_list
    assert not result.order_conflicts
    assert not result.id_conflicts
    assert not result.name_joins
    assert result.only_in == ((), ())


def test_deterministic() -> None:
    inputs = [
        _list(_numbers(1, 2, 3, 4)),
        _list(_numbers(1, 5, 3, 2), description="b"),
        _list(_numbers(6, 1), ordered=False),
    ]
    assert combine(inputs) == combine(inputs)


def test_adding_an_input_never_reorders_the_backbone() -> None:
    backbone = _list(_numbers(1, 2, 3, 4, 5))
    other = _list(_numbers(5, 9, 3, 1, 8, 2))
    result = combine([backbone, other]).reading_list
    kept = [name for name in _issues(result) if name in {"1", "2", "3", "4", "5"}]
    assert kept == ["1", "2", "3", "4", "5"]
    assert set(_issues(result)) == {"1", "2", "3", "4", "5", "8", "9"}


def test_an_existing_order_passed_first_is_kept() -> None:
    curated = _list(_numbers(1, 2, 3, 4))
    hand_reordered = _list(_numbers(4, 2, 1, 3))
    result = combine([hand_reordered, curated])
    assert _issues(result.reading_list) == ["4", "2", "1", "3"]
    assert len(result.order_conflicts) > 0


def test_two_sources_of_one_list() -> None:
    comicvine = _list([_entry(n, comicvine=f"cv{n}") for n in (1, 2, 3)])
    metron = _list(
        [_entry(n, year=None, metron=f"m{n}", comicvine=f"cv{n}") for n in (1, 2, 3)]
    )
    result = combine([comicvine, metron])
    entries = result.reading_list[ENTRIES_KEY]
    assert [entry["identifiers"] for entry in entries] == [
        {"comicvine": {"key": f"cv{n}"}, "metron": {"key": f"m{n}"}} for n in (1, 2, 3)
    ]
    assert result.provenance == tuple(
        (EntryOrigin(0, row), EntryOrigin(1, row)) for row in range(3)
    )
    assert result.only_in == ((), ())
    assert not result.name_joins


def test_tags_subset_against_a_full_list() -> None:
    tags = _list(
        [_entry(n, comicvine=f"cv{n}") for n in (6, 2)],
        name="tags",
        ordered=False,
        sources=[{"kind": "tags"}, {"kind": "metron-arc", "key": "17"}],
    )
    curated = _list(
        [_entry(n, comicvine=f"cv{n}") for n in range(1, 8)],
        description="Curated.",
        sources=[{"kind": "metron-arc", "key": "17", "revision": "r1"}],
    )
    result = combine([tags, curated])
    reading_list = result.reading_list
    assert _issues(reading_list) == ["1", "2", "3", "4", "5", "6", "7"]
    assert reading_list["name"] == "Civil War"
    assert reading_list["description"] == "Curated."
    assert reading_list["ordered"] is True
    # The pointer and the fetched arc are one source.
    assert reading_list["sources"] == [
        {"kind": "tags"},
        {"kind": "metron-arc", "key": "17", "revision": "r1"},
    ]
    assert result.only_in == ((), (0, 2, 3, 4, 6))
    assert result.provenance[1] == (EntryOrigin(0, 1), EntryOrigin(1, 1))


def test_two_orders_of_one_event() -> None:
    first = _list(_numbers(1, 2, 3, 4, 5))
    second = _list(_numbers(1, 4, 2, 3, 5))
    result = combine([first, second])
    assert _issues(result.reading_list) == ["1", "2", "3", "4", "5"]
    assert result.order_conflicts == (OrderConflict(entry=3, input_index=1, row=1),)


def test_an_ordered_input_inserts_after_its_anchor() -> None:
    first = _list(_numbers(1, 2, 3))
    second = _list(_numbers(1, 7, 8, 3, 9))
    result = combine([first, second])
    assert _issues(result.reading_list) == ["1", "7", "8", "2", "3", "9"]
    assert result.only_in == ((3,), (1, 2, 5))


def test_three_inputs_joined_only_transitively() -> None:
    comicvine = _list([_entry(n, comicvine=f"cv{n}") for n in (1, 2)])
    both = _list(
        [
            _entry(
                n,
                series="Civil War (2006)",
                year=None,
                comicvine=f"cv{n}",
                metron=f"m{n}",
            )
            for n in (1, 2)
        ]
    )
    metron = _list([_entry(n, series="CW", metron=f"m{n}") for n in (1, 2)])
    result = combine([comicvine, metron, both])
    assert len(result.reading_list[ENTRIES_KEY]) == 2
    assert result.provenance[0] == (
        EntryOrigin(0, 0),
        EntryOrigin(1, 0),
        EntryOrigin(2, 0),
    )


def test_a_repeated_issue_in_both_inputs() -> None:
    result = combine([_list(_numbers(1, 2, 1)), _list(_numbers(1, 2, 1))])
    assert _issues(result.reading_list) == ["1", "2", "1"]
    assert result.only_in == ((), ())


def test_a_repeated_issue_in_one_input() -> None:
    result = combine([_list(_numbers(1, 2, 1)), _list(_numbers(1, 2))])
    assert _issues(result.reading_list) == ["1", "2", "1"]
    assert result.only_in == ((2,), ())


def test_an_id_disagreement_through_a_name_join() -> None:
    first = _list([_entry(1, comicvine="105747")])
    second = _list([_entry(1, comicvine="999", upc="75960605421300111")])
    third = _list([_entry(1, upc="75960605421300211")])
    result = combine([first, second, third])
    (entry,) = result.reading_list[ENTRIES_KEY]
    assert entry["identifiers"]["comicvine"] == {"key": "105747"}
    assert result.id_conflicts == (
        IdConflict(
            entry=0,
            source="comicvine",
            kept="105747",
            dropped="999",
            input_index=1,
            row=0,
        ),
    )
    # A different barcode is another printing, not a bad mapping.
    assert entry["identifiers"]["upc"] == {"key": "75960605421300111"}
    assert result.name_joins == (0,)


def test_a_row_shared_by_two_ids_goes_to_the_better_ranked_one() -> None:
    """A row of B carries the ids of two rows of A; Metron outranks ComicVine."""
    first = _list(
        [_entry(1, year=None, comicvine="100"), _entry(2, year=None, metron="5")]
    )
    second = _list([_entry(1, year=None, comicvine="100", metron="5")])
    result = combine([first, second])
    assert result.provenance == (
        (EntryOrigin(0, 0),),
        (EntryOrigin(0, 1), EntryOrigin(1, 0)),
    )
    # A refused link is no disagreement: the joined rows' ids agree.
    assert result.id_conflicts == ()


def test_an_id_match_is_never_lost_to_a_name_match() -> None:
    """C's one book shares a name with a's first and an id with a's third."""
    books = [
        _entry(1, comicvine="105747"),
        _entry(2, comicvine="106000"),
        _entry(1, comicvine="999001"),
    ]
    a, b = _list(books), _list(books)
    c = _list([_entry(1, comicvine="999001")])
    result = combine([a, b, c])
    ids = [
        entry["identifiers"]["comicvine"]["key"]
        for entry in result.reading_list[ENTRIES_KEY]
    ]
    assert ids == ["105747", "106000", "999001"]
    assert result.id_conflicts == ()
    assert result.provenance[2] == (
        EntryOrigin(0, 2),
        EntryOrigin(1, 2),
        EntryOrigin(2, 0),
    )


def test_an_id_match_takes_the_repeat_it_names() -> None:
    """X and X' share a name key; C's row carries X' id, so it joins X'."""
    first = _list(
        [
            _entry(1, comicvine="cv1"),
            _entry(5, series="Other"),
            _entry(1, comicvine="cv2"),
        ]
    )
    second = _list([_entry(1, comicvine="cv2")])
    result = combine([first, second])
    assert result.provenance == (
        (EntryOrigin(0, 0),),
        (EntryOrigin(0, 1),),
        (EntryOrigin(0, 2), EntryOrigin(1, 0)),
    )
    assert result.id_conflicts == ()


@dataclass(frozen=True, slots=True)
class _Issue:
    series: str
    number: int
    year: int
    comicvine: str
    metron: str


def _random_inputs(seed: int) -> list[dict[str, Any]]:
    """
    Build lists of one pool of issues with consistent ids, some dropped.

    Every third issue has a twin with the same series, year and number and
    ids of its own, as a reprint has: rows a name key cannot tell apart.
    """
    rng = random.Random(seed)  # noqa: S311 - a test fixture, not a secret
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
    inputs = []
    for _ in range(rng.randint(2, 4)):
        rows = []
        for issue in rng.sample(pool, rng.randint(6, 18)):
            row = _random_row(rng, issue)
            rows.extend([row, row] if rng.random() < 0.1 else [row])
        inputs.append(_list(rows))
    return inputs


def _random_row(rng: random.Random, issue: _Issue) -> dict[str, Any]:
    """Write one issue as a list might: some ids, maybe no year."""
    row = _entry(
        issue.number,
        series=issue.series,
        year=issue.year if rng.random() < 0.7 else None,
    )
    ids = (("comicvine", issue.comicvine), ("metron", issue.metron))
    if identifiers := {
        source: {"key": key} for source, key in ids if rng.random() < 0.6
    }:
        row["identifiers"] = identifiers
    return row


def _id_counts(entries: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(
        (source, identifier["key"])
        for entry in entries
        for source, identifier in (entry.get("identifiers") or {}).items()
    )


@pytest.mark.parametrize("seed", range(40))
def test_no_id_lands_on_two_entries_unless_an_input_repeats_it(seed: int) -> None:
    inputs = _random_inputs(seed)
    result = combine(inputs)
    repeated = {
        id_key
        for reading_list in inputs
        for id_key, count in _id_counts(reading_list[ENTRIES_KEY]).items()
        if count > 1
    }
    for id_key, count in _id_counts(result.reading_list[ENTRIES_KEY]).items():
        assert count == 1 or id_key in repeated, id_key
    for members in result.provenance:
        assert len({origin.input_index for origin in members}) == len(members)


def test_new_entries_with_nothing_in_common_go_after_the_primary() -> None:
    result = combine([_list(_numbers(1, 2, 3)), _list(_numbers(7, 8, 9))])
    assert _issues(result.reading_list) == ["1", "2", "3", "7", "8", "9"]


def test_new_entries_before_any_common_one_go_just_before_it() -> None:
    result = combine([_list(_numbers(1, 2, 3, 4, 5)), _list(_numbers(9, 4))])
    assert _issues(result.reading_list) == ["1", "2", "3", "9", "4", "5"]


def test_a_merged_date_never_contradicts_itself() -> None:
    year_only = _list([{**_entry(1), "date": {"year": 2006}}])
    other_year = _list(
        [
            {
                **_entry(1),
                "date": {
                    "cover_date": date(2007, 1, 1),
                    "store_date": date(2006, 12, 20),
                    "year": 2007,
                    "month": 1,
                    "day": 1,
                },
            }
        ]
    )
    same_year = _list(
        [{**_entry(1), "date": {"cover_date": date(2006, 3, 1), "month": 3}}]
    )
    (entry,) = combine([year_only, other_year]).reading_list[ENTRIES_KEY]
    assert entry["date"] == {"year": 2006, "store_date": date(2006, 12, 20)}
    (entry,) = combine([year_only, same_year]).reading_list[ENTRIES_KEY]
    assert entry["date"] == {"year": 2006, "cover_date": date(2006, 3, 1), "month": 3}


def test_an_unordered_input_is_placed_by_date() -> None:
    jan, feb, mar, apr, may = (date(2006, month, 1) for month in (1, 2, 3, 4, 5))
    backbone = _list(
        [_entry(n, cover=when) for n, when in ((1, jan), (3, mar), (5, may))]
    )
    unordered = _list(
        [
            _entry(9),
            _entry(4, cover=apr),
            _entry(2, cover=feb),
            _entry(0, cover=date(2005, 12, 1)),
        ],
        ordered=False,
    )
    result = combine([backbone, unordered])
    assert _issues(result.reading_list) == ["0", "1", "2", "3", "4", "5", "9"]


def test_an_unordered_input_with_an_undated_backbone_goes_last() -> None:
    backbone = _list(_numbers(1, 2))
    unordered = _list([_entry(3, cover=date(2006, 1, 1))], ordered=False)
    assert _issues(combine([backbone, unordered]).reading_list) == ["1", "2", "3"]


def test_no_ordered_input_sorts_by_date_series_and_issue() -> None:
    first = _list(
        [
            _entry(3, cover=date(2006, 3, 1)),
            _entry(1, series="Zzz", cover=date(2006, 1, 1)),
            _entry(1, series="Aaa", cover=date(2006, 1, 1)),
            _entry(7),
        ],
        ordered=False,
    )
    second = _list([_entry(2, cover=date(2006, 2, 1)), _entry(6)], ordered=False)
    result = combine([first, second]).reading_list
    assert [
        (entry["series"]["name"], entry["issue"]["name"])
        for entry in result[ENTRIES_KEY]
    ] == [
        ("Aaa", "1"),
        ("Zzz", "1"),
        ("Civil War", "2"),
        ("Civil War", "3"),
        ("Civil War", "6"),
        ("Civil War", "7"),
    ]
    assert result["ordered"] is False


def test_fields_first_value_wins_and_ids_union() -> None:
    first = _list(
        [
            {
                "series": {"name": "Civil War", "start_year": 2006},
                "issue": {"name": "1"},
                "identifiers": {"comicvine": {"key": "1"}},
            }
        ],
        tags={"a"},
    )
    second = _list(
        [
            {
                "series": {
                    "name": "CIVIL WAR",
                    "start_year": 2006,
                    "identifiers": {"comicvine": {"key": "18023"}},
                },
                "volume": {"number": 1},
                "issue": {"name": "1"},
                "date": {"cover_date": date(2006, 7, 1)},
                "identifiers": {"metron": {"key": "2"}},
                "entry_type": "core",
            }
        ],
        name="Other",
        tags={"b"},
        private=False,
        sources=[{"kind": "file", "curator": "x"}],
    )
    result = combine([first, second]).reading_list
    assert result["name"] == "Civil War"
    assert result["tags"] == {"a", "b"}
    assert result["private"] is False
    assert result[ENTRIES_KEY] == [
        {
            "series": {
                "name": "Civil War",
                "start_year": 2006,
                "identifiers": {"comicvine": {"key": "18023"}},
            },
            "volume": {"number": 1},
            "issue": {"name": "1"},
            "date": {"cover_date": date(2006, 7, 1)},
            "identifiers": {"comicvine": {"key": "1"}, "metron": {"key": "2"}},
            "entry_type": "core",
        }
    ]


def test_keyless_sources_merge_only_when_equal() -> None:
    first = _list(_numbers(1), sources=[{"kind": "file", "curator": "a"}])
    second = _list(_numbers(1), sources=[{"kind": "file", "curator": "b"}])
    third = _list(_numbers(1), sources=[{"kind": "file", "curator": "a"}])
    result = combine([first, second, third]).reading_list
    assert result["sources"] == [
        {"kind": "file", "curator": "a"},
        {"kind": "file", "curator": "b"},
    ]


def test_inputs_are_validated() -> None:
    raw = {"reading_list": _list([{**_entry(1), "bogus": 1}], list_type="Event")}
    result = combine([raw]).reading_list
    assert result == load_model(raw)
    assert result["list_type"] == "event"


def test_a_large_pair_combines_quickly() -> None:
    def entry(number: int) -> dict[str, Any]:
        return _entry(
            number,
            series=f"Series {number % 97}",
            cover=date(2000, 1, 1) + timedelta(days=number),
            comicvine=str(100000 + number),
        )

    first = _list([entry(n) for n in range(3000)])
    rows = [entry(n) for n in range(3000)]
    rows[100:200] = reversed(rows[100:200])
    second = _list(rows[:2800] + [entry(n) for n in range(3000, 3200)])
    timings = []
    for _ in range(3):
        start = time.perf_counter()
        combine([first, second])
        timings.append(time.perf_counter() - start)
    assert min(timings) < 1.0
    assert len(combine([first, second]).reading_list[ENTRIES_KEY]) == 3200
