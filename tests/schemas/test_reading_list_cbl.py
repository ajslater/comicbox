"""ComicRack ``.cbl`` reading lists, from hand-written fixtures."""

from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    ReadingListFormats,
    SmartListError,
    detect_format,
    dumps,
    load,
    loads,
    lost_fields,
)
from comicbox.readinglists.formats.cbl.transform import MAX_START_YEAR
from tests.const import TEST_FILES_DIR

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
CBL_DIR = READING_LISTS_DIR / "cbl"
READABLE = sorted(path for path in CBL_DIR.glob("*.cbl") if path.stem != "smart-list")


def _entries(name: str) -> list[dict[str, Any]]:
    return load(CBL_DIR / name).reading_list[ENTRIES_KEY]


def test_common_shape() -> None:
    result = load(CBL_DIR / "common.cbl")
    assert result.fmt is ReadingListFormats.CBL
    assert result.warnings == ()
    reading_list = result.reading_list
    assert reading_list["name"] == "[Marvel] Crimson Tide (Hand Written)"
    assert reading_list["sources"] == [{"kind": "file"}]
    assert reading_list[ENTRIES_KEY][1] == {
        "series": {
            "name": "The Amazing Snail-Man",
            "start_year": 1963,
            "identifiers": {"comicvine": {"key": "2127"}},
        },
        "volume": {"number": 1963},
        "issue": {"name": "532"},
        "date": {"year": 2006},
        "identifiers": {"comicvine": {"key": "105800"}},
    }


def test_two_databases() -> None:
    entries = _entries("two-databases.cbl")
    assert [entry["identifiers"] for entry in entries] == [
        {"comicvine": {"key": "105747"}, "metron": {"key": "31562"}},
        {"comicvine": {"key": "106000"}, "metron": {"key": "31563"}},
    ]
    assert entries[0]["series"]["identifiers"] == {
        "comicvine": {"key": "18023"},
        "metron": {"key": "1046"},
    }


def test_no_num_issues() -> None:
    assert len(_entries("no-numissues.cbl")) == 2


def test_start_year_and_source() -> None:
    reading_list = load(CBL_DIR / "startyear-source.cbl").reading_list
    assert reading_list["start_year"] == 2006
    assert reading_list["sources"] == [{"kind": "file", "curator": "CBRO"}]


def test_native_comicrack_export() -> None:
    """Id, FileName and Format are ignored; a small Volume is no year."""
    result = load(CBL_DIR / "comicrack-native.cbl")
    assert result.warnings == ()
    assert result.reading_list[ENTRIES_KEY] == [
        {
            "series": {"name": "Crimson Tide"},
            "volume": {"number": 1},
            "issue": {"name": "1"},
            "date": {"year": 2006},
        },
        {
            "series": {"name": "Amazing Snail-Man"},
            "volume": {"number": 2},
            "issue": {"name": "532"},
            "date": {"year": 2006},
        },
    ]


def test_single_book() -> None:
    (entry,) = _entries("single-book.cbl")
    assert entry["issue"] == {"name": "1"}


def test_a_smart_list_raises() -> None:
    with pytest.raises(SmartListError):
        load(CBL_DIR / "smart-list.cbl")


def test_one_bad_row_is_skipped() -> None:
    result = load(CBL_DIR / "bad-row.cbl")
    assert [entry["issue"]["name"] for entry in result.reading_list[ENTRIES_KEY]] == [
        "1",
        "2",
    ]
    assert result.warnings == ("Book 2: no series or number; skipped.",)


def test_an_unknown_database_drops_the_child_and_keeps_the_row() -> None:
    result = load(CBL_DIR / "none-database.cbl")
    (entry,) = result.reading_list[ENTRIES_KEY]
    assert entry["identifiers"] == {"comicvine": {"key": "105747"}}
    assert result.warnings == ("Book 1: unknown database 'none'; its ids are dropped.",)


def _book(volume: str) -> str:
    return (
        "<ReadingList><Name>A</Name><Books>"
        f'<Book Series="A" Number="1" Volume="{volume}" />'
        "</Books><Matchers /></ReadingList>"
    )


@pytest.mark.parametrize(
    ("volume", "start_year", "number"),
    [
        ("2006", 2006, 2006),
        ("1900", 1900, 1900),
        ("2", None, 2),
        ("1899", None, 1899),
        (str(MAX_START_YEAR + 1), None, MAX_START_YEAR + 1),
        ("vol", None, None),
    ],
)
def test_volume_as_a_year_or_a_volume(
    volume: str, start_year: int | None, number: int | None
) -> None:
    """Community files put the start year in Volume; ComicRack, a number."""
    (entry,) = loads(_book(volume)).reading_list[ENTRIES_KEY]
    assert entry["series"].get("start_year") == start_year
    assert entry.get("volume", {}).get("number") == number


def test_detected_by_its_root() -> None:
    text = (CBL_DIR / "common.cbl").read_text()
    assert detect_format(text) is ReadingListFormats.CBL
    assert detect_format(text.replace("ReadingList", "ReadingLists")) is None


@pytest.mark.parametrize("path", READABLE, ids=[path.stem for path in READABLE])
def test_round_trip(path: Path) -> None:
    reading_list = load(path).reading_list
    text = dumps(reading_list, ReadingListFormats.CBL)
    assert loads(text).reading_list == reading_list
    assert "<Matchers/>" in text


def test_write_counts_the_books_it_writes() -> None:
    reading_list = {
        "name": "A",
        ENTRIES_KEY: [
            {"series": {"name": "A"}, "issue": {"name": "1"}},
            {"series": {"name": "A"}},
            {"series": {"name": "A"}, "issue": {"number": 2}},
        ],
    }
    text = dumps(reading_list, "cbl")
    assert "<NumIssues>2</NumIssues>" in text
    assert 'Number="2"' in text
    # The second is not written; the third's number is written as its name.
    assert lost_fields(reading_list, "cbl") == (
        "sources",
        "entries.issue.name",
        "entries.issue.number",
        "entries #2",
    )


def test_lost_fields_name_what_a_round_trip_drops() -> None:
    reading_list = load(READING_LISTS_DIR / "crimson-tide.yaml").reading_list
    lost = lost_fields(reading_list, "cbl")
    assert lost == (
        "description",
        "end_year",
        "list_type",
        "next",
        "notes",
        "previous",
        "sources",
        "tags",
        "entries.date.cover_date",
        "entries.date.month",
        "entries.date.store_date",
        "entries.date.year",
        "entries.entry_type",
        "entries.notes",
        "entries.volume.number",
    )
    round_tripped = loads(dumps(reading_list, "cbl")).reading_list
    for key in ("description", "end_year", "list_type", "next", "previous", "tags"):
        assert key in reading_list
        assert key not in round_tripped
    assert round_tripped["sources"] == [{"kind": "file", "curator": "cbro"}]
    for entry in round_tripped[ENTRIES_KEY]:
        assert "entry_type" not in entry
        assert set(entry["date"]) == {"year"}
    # Amazing Snail-Man's volume 2 was written over by its start year.
    assert round_tripped[ENTRIES_KEY][1]["volume"] == {"number": 1999}


def test_other_databases_are_lost() -> None:
    reading_list = {
        "name": "A",
        ENTRIES_KEY: [
            {
                "series": {
                    "name": "A",
                    "identifiers": {"grandcomicsdatabase": {"key": "1"}},
                },
                "issue": {"name": "1"},
                "identifiers": {
                    "comicvine": {"key": "2"},
                    "grandcomicsdatabase": {"key": "3"},
                },
            }
        ],
    }
    assert lost_fields(reading_list, "cbl") == (
        "sources",
        "entries.identifiers.grandcomicsdatabase",
        "entries.series.identifiers.grandcomicsdatabase",
    )


@pytest.mark.parametrize(
    ("flags", "lost"),
    [
        ({"ordered": False}, ("ordered",)),
        ({"ordered": True, "private": False}, ()),
        ({"private": True}, ("private",)),
        ({}, ()),
    ],
)
def test_only_a_flag_off_its_default_is_lost(
    flags: dict[str, bool], lost: tuple[str, ...]
) -> None:
    """CBL lists are reading orders and public; only the opposite is lost."""
    reading_list = {
        "name": "A",
        "sources": [{"kind": "file"}],
        ENTRIES_KEY: [{"series": {"name": "A"}, "issue": {"name": "1"}}],
        **flags,
    }
    assert lost_fields(reading_list, "cbl") == lost
