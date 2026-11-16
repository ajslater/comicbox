"""A read names everything it drops or changes, and never guesses a day."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.readinglists import ENTRIES_KEY, dumps, entry_keys, load, loads
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
MINIMAL_JSON_CBL = READING_LISTS_DIR / "json-cbl" / "minimal.json"
_YAML_HEADER = "reading_list:\n  name: A\n"


def _yaml(body: str) -> tuple[str, ...]:
    return loads(_YAML_HEADER + body).warnings


@pytest.mark.parametrize(
    ("body", "warning"),
    [
        ("  descripton: typo\n", "descripton: 'typo' dropped"),  # codespell:ignore
        (
            "  entires:\n    - series: {name: A}\n",  # codespell:ignore
            "entires: [{'series': {'name': 'A'}}] dropped",  # codespell:ignore
        ),
        (
            "  entries:\n    - series: {name: A}\n      entry_typ: core\n",
            "entries #1.entry_typ: 'core' dropped",
        ),
        (
            "  entries:\n    - series: {name: A, publisher: Marvel}\n",
            "entries #1.series.publisher: 'Marvel' dropped",
        ),
        ("  ordered: maybe\n", "ordered: 'maybe' dropped"),
        ("  start_year: abc\n", "start_year: 'abc' dropped"),
        (
            "  entries:\n    - series: Batman\n      issue: {name: '1'}\n",
            "entries #1.series: 'Batman' read as {'name': 'Batman'}",
        ),
        (
            "  entries:\n    - series: {name: A}\n      volume: 2006\n",
            "entries #1.volume: 2006 read as {'number': 2006}",
        ),
        (
            "  entries:\n    - series: {name: A}\n      volume: {number: -1}\n",
            "entries #1.volume.number: -1 read as 0",
        ),
        (
            "  entries:\n    - 1\n    - series: {name: A}\n",
            "entries #1: 1 is not an entry; dropped",
        ),
        (
            "  entries:\n    - series: {name: A}\n    - a\n",
            "entries #2: 'a' is not an entry; dropped",
        ),
    ],
    ids=[
        "unknown-key",
        "unknown-list",
        "unknown-entry-key",
        "unknown-series-key",
        "bad-boolean",
        "bad-integer",
        "plain-string-series",
        "plain-number-volume",
        "clamped-number",
        "number-entry",
        "string-entry",
    ],
)
def test_a_read_names_what_it_drops(body: str, warning: str) -> None:
    assert warning in _yaml(body)


def test_equal_meanings_are_not_changes() -> None:
    """``1`` read as ``"1"`` and ``Event`` as ``event`` lose nothing."""
    body = (
        "  list_type: Event\n  ordered: true\n  tags: [b, a]\n"
        "  entries:\n    - series: {name: A, start_year: 2006}\n"
        "      issue: {name: 1}\n      date: {cover_date: 2006-07-01}\n"
    )
    assert _yaml(body) == ()


# Every fixture but the ones written to warn or to fail.
_CLEAN_FIXTURES = (
    READING_LISTS_DIR / "civil-war.yaml",
    *(
        path
        for path in sorted((READING_LISTS_DIR / "cbl").glob("*.cbl"))
        if path.stem not in {"bad-row", "none-database", "smart-list"}
    ),
    MINIMAL_JSON_CBL,
)


@pytest.mark.parametrize(
    "path", _CLEAN_FIXTURES, ids=[path.name for path in _CLEAN_FIXTURES]
)
def test_clean_fixtures_read_without_warnings(path: Path) -> None:
    assert load(path).warnings == ()


def test_a_cbl_reads_its_own_names() -> None:
    cbl = (
        "<ReadingList><Name>A</Name><StartYear>abc</StartYear><Nmae>x</Nmae>"  # codespell:ignore
        "<Books><Book Series='A' Number='1' /></Books><Matchers /></ReadingList>"
    )
    assert loads(cbl).warnings == (
        "ReadingList.StartYear: 'abc' dropped",
        "ReadingList.Nmae: 'x' dropped",  # codespell:ignore
    )


def test_empty_books_count_toward_positions() -> None:
    cbl = (
        "<ReadingList><Name>A</Name><Books><Book /><Book Series='A' />"
        "<Book Series='A' Number='1' /></Books><Matchers /></ReadingList>"
    )
    assert loads(cbl).warnings == (
        "Book 1: no series or number; skipped.",
        "Book 2: no series or number; skipped.",
    )


@pytest.fixture
def log_lines() -> Iterator[list[str]]:
    lines: list[str] = []
    handler = logger.add(lines.append, level="DEBUG")
    try:
        yield lines
    finally:
        logger.remove(handler)


def test_warnings_are_returned_not_logged(log_lines: list[str]) -> None:
    warnings = _yaml(
        "  ordered: maybe\n  entries:\n    - series: {name: A}\n"
        "      volume: {number: -1}\n"
    )
    assert len(warnings) == 2
    assert not [line for line in log_lines if "WARNING" in line]


def _cover_date(value: str) -> tuple[dict[str, Any], tuple[str, ...]]:
    document = json.loads(MINIMAL_JSON_CBL.read_text())
    document["issueList"][0]["issueCoverDate"] = value
    result = loads(json.dumps(document))
    return result.reading_list[ENTRIES_KEY][0], result.warnings


@pytest.mark.parametrize(
    ("value", "entry_date", "warning"),
    [
        (
            "2006-07",
            {"year": 2006, "month": 7},
            (
                "entries #1.date.cover_date: '2006-07' is not a whole date;"
                " read as year 2006, month 7"
            ),
        ),
        (
            "2006",
            {"year": 2006},
            "entries #1.date.cover_date: '2006' is not a whole date; read as year 2006",
        ),
        (
            # Read as a comic's date is (AJ: "Yes, read them").
            "July 2006",
            {"year": 2006, "month": 7},
            (
                "entries #1.date.cover_date: 'July 2006' is not a whole date;"
                " read as year 2006, month 7"
            ),
        ),
        (
            "July 15, 2006",
            {"cover_date": date(2006, 7, 15)},
            "entries #1.date.cover_date: 'July 15, 2006' read as 2006-07-15",
        ),
        (
            "07/15/2006",
            {"cover_date": date(2006, 7, 15)},
            "entries #1.date.cover_date: '07/15/2006' read as 2006-07-15",
        ),
        ("2006-02-30", None, "entries #1.date.cover_date: '2006-02-30' dropped"),
        ("soon", None, "entries #1.date.cover_date: 'soon' dropped"),
    ],
)
def test_a_cover_date_is_never_completed_from_today(
    value: str, entry_date: dict[str, Any] | None, warning: str
) -> None:
    entry, warnings = _cover_date(value)
    assert entry.get("date") == entry_date
    assert warnings == (warning,)


def test_a_yaml_date_is_read_as_a_comics_and_written_as_iso() -> None:
    result = loads(
        "reading_list:\n  name: X\n  entries:\n"
        "    - series: {name: A}\n      date: {store_date: 15 Jul 2006}\n"
        "    - series: {name: B}\n      date: {cover_date: 2006}\n",
        fmt="yaml",
    )

    first, second = result.reading_list[ENTRIES_KEY]
    assert first["date"] == {"store_date": date(2006, 7, 15)}
    # An unquoted YAML 2006 is a number, and still a year.
    assert second["date"] == {"year": 2006}
    assert result.warnings == (
        "entries #1.date.store_date: '15 Jul 2006' read as 2006-07-15",
        "entries #2.date.cover_date: 2006 is not a whole date; read as year 2006",
    )
    assert "store_date: 2006-07-15" in dumps(result.reading_list, "yaml")


def test_a_partial_yaml_store_date_is_dropped() -> None:
    warnings = _yaml(
        "  entries:\n    - series: {name: A}\n      date: {store_date: '2006-07'}\n"
    )
    assert warnings == (
        "entries #1.date.store_date: '2006-07' is not a whole date; dropped",
    )


def _book(volume: str, year: str) -> str:
    return (
        "<ReadingList><Name>A</Name><Books>"
        f"<Book Series='Batman' Number='1' Volume='{volume}' Year='{year}' />"
        "</Books><Matchers /></ReadingList>"
    )


def test_minus_one_is_comicrack_for_unknown() -> None:
    result = loads(_book("-1", "-1"))
    (entry,) = result.reading_list[ENTRIES_KEY]
    assert entry == {"series": {"name": "Batman"}, "issue": {"name": "1"}}
    assert result.warnings == ()
    # Without a volume there is no name key, so Batman (1940) #1 and
    # Batman (2011) #1 written with Volume="-1" are never one issue.
    assert entry_keys(entry) == ()


def test_other_negatives_are_dropped_with_a_warning() -> None:
    result = loads(_book("-5", "-2006"))
    (entry,) = result.reading_list[ENTRIES_KEY]
    assert "volume" not in entry
    assert "date" not in entry
    assert result.warnings == (
        "Book 1: Volume '-5' dropped.",
        "Book 1: Year '-2006' dropped.",
    )


# ------------------------------------------- drops in survivors (R2-E E5)


def test_drops_inside_the_items_a_list_keeps_are_named() -> None:
    warnings = _yaml(
        '  sources: [{kind: file, bogus: 1, curator: [a, b]}, "a string"]\n'
    )
    assert warnings == (
        "sources: 1 of 2 items dropped",
        "sources #1.bogus: 1 dropped",
        "sources #1.curator: ['a', 'b'] dropped",
    )


def test_a_dropped_item_before_a_survivor_does_not_shift_its_path() -> None:
    warnings = _yaml('  sources: ["a string", {kind: url, bogus: 1}]\n')
    assert warnings == (
        "sources: 1 of 2 items dropped",
        "sources #2.bogus: 1 dropped",
    )


def test_drops_inside_kept_alternative_names_are_named() -> None:
    warnings = _yaml(
        "  entries:\n"
        "    - series: {name: S, alternative_names: [7, {name: Other, bogus: 2}]}\n"
        '      issue: {name: "1"}\n'
    )
    assert "entries #1.series.alternative_names: 1 of 2 items dropped" in warnings
    assert "entries #1.series.alternative_names #2.bogus: 2 dropped" in warnings


def test_drops_inside_kept_json_cbl_ids_are_named() -> None:
    document = {
        "fileDetails": {"version": 1.0, "UUID": "be7545a2-7a69-4bbc-ba0e-a4e2eea68d67"},
        "listDetails": {"name": "A"},
        "issueList": [
            {
                "seriesName": "S",
                "seriesStartYear": 2006,
                "issueNumber": "1",
                "issueCoverDate": "2006-07-01",
                "id": [
                    "junk",
                    {"name": "comicvine", "series": "1", "issue": "2", "bogus": 3},
                ],
            }
        ],
    }
    warnings = loads(json.dumps(document)).warnings
    assert "issueList #1.id: 1 of 2 items dropped" in warnings
    assert "issueList #1.id #2.bogus: 3 dropped" in warnings


def test_pairing_a_long_list_with_drops_stays_linear() -> None:
    import time

    items = ", ".join(
        "x" if position % 2 else f"{{kind: url, key: k{position}, bogus: 1}}"
        for position in range(4000)
    )
    started = time.monotonic()
    warnings = _yaml(f"  sources: [{items}]\n")
    assert time.monotonic() - started < 5
    assert warnings[0] == "sources: 2000 of 4000 items dropped"
    assert "sources #4.bogus: 1 dropped" not in warnings  # #4 was "x"
    assert "sources #3.bogus: 1 dropped" in warnings


def test_a_second_cbl_database_of_one_name_is_a_warning() -> None:
    result = loads(
        "<ReadingList><Name>A</Name><Books>"
        '<Book Series="S" Number="1" Volume="2006" Year="2006">'
        '<Database Name="cv" Series="1" Issue="2" />'
        '<Database Name="cv" Series="3" Issue="4" />'
        "</Book></Books></ReadingList>"
    )
    assert result.warnings == (
        "Book 1: a second 'cv' database; its ids replace the first's.",
    )
    assert result.reading_list["entries"][0]["identifiers"]["comicvine"]["key"] == "4"


@pytest.mark.parametrize(
    "text",
    [
        "reading_list:\n  name: A\nschema: x\nbogus: 1\n",
        '{"reading_list": {"name": "A"}, "schema": "x", "bogus": 1}',
    ],
    ids=["yaml", "json"],
)
def test_root_keys_beside_the_list_are_named(text: str) -> None:
    assert loads(text).warnings == ("bogus: 1 dropped",)
