"""A read names everything it drops or changes, and never guesses a day."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.readinglists import ENTRIES_KEY, entry_keys, load, loads
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
            "entries #1.series: 'Batman' dropped",
        ),
        (
            "  entries:\n    - series: {name: A}\n      volume: 2006\n",
            "entries #1.volume: 2006 dropped",
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
            "July 2006",
            None,
            "entries #1.date.cover_date: 'July 2006' dropped",
        ),
        ("2006-02-30", None, "entries #1.date.cover_date: '2006-02-30' dropped"),
    ],
)
def test_a_cover_date_is_never_completed_from_today(
    value: str, entry_date: dict[str, int] | None, warning: str
) -> None:
    entry, warnings = _cover_date(value)
    assert entry.get("date") == entry_date
    assert warnings == (warning,)


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
