"""json-cbl 1.0 reading lists, checked against the vendored spec."""

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    ReadingListFormats,
    detect_format,
    dumps,
    load,
    loads,
    lost_fields,
)
from comicbox.readinglists.formats.json_cbl.transform import CURATORS
from comicbox.validate.spec import build_validator
from tests.const import TEST_FILES_DIR

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
JSON_CBL_DIR = READING_LISTS_DIR / "json-cbl"
FIXTURES = sorted(JSON_CBL_DIR.glob("*.json"))
FULL_PATH = JSON_CBL_DIR / "full.json"
MINIMAL_PATH = JSON_CBL_DIR / "minimal.json"
_SPEC = ReadingListFormats.JSON_CBL.value.validator_spec


def _validate(text: str) -> None:
    assert _SPEC is not None
    build_validator(_SPEC).validate(text)


def _entry(**fields: Any) -> dict[str, Any]:
    return {
        "series": {"name": "Civil War", "start_year": 2006},
        "issue": {"name": "1"},
        "date": {"cover_date": date(2006, 7, 1)},
        **fields,
    }


def _list(*entries: dict[str, Any], **header: Any) -> dict[str, Any]:
    return {"name": "Civil War", ENTRIES_KEY: list(entries or [_entry()]), **header}


def _written(reading_list: dict[str, Any]) -> dict[str, Any]:
    text = dumps(reading_list, ReadingListFormats.JSON_CBL)
    _validate(text)
    return json.loads(text)


@pytest.mark.parametrize("path", FIXTURES, ids=[path.stem for path in FIXTURES])
def test_fixtures_follow_the_spec(path: Path) -> None:
    _validate(path.read_text())


@pytest.mark.parametrize(
    "path",
    [
        FULL_PATH,
        MINIMAL_PATH,
        READING_LISTS_DIR / "cbl" / "common.cbl",
        READING_LISTS_DIR / "cbl" / "comicrack-native.cbl",
        READING_LISTS_DIR / "civil-war.yaml",
    ],
    ids=lambda path: path.name,
)
def test_what_comicbox_writes_follows_the_spec(path: Path) -> None:
    _written(load(path).reading_list)


def test_full_document() -> None:
    result = load(FULL_PATH)
    assert result.fmt is ReadingListFormats.JSON_CBL
    assert result.warnings == (
        "listDetails publisher, imprint, coverImageURLs dropped: the model has no place.",
    )
    expected = {
        "list_type": "characters",
        "ordered": True,
        "start_year": 2006,
        "end_year": 2007,
        "tags": {"crossover", "marvel"},
        "notes": "Free text.",
        "sources": [
            {
                "kind": "json-cbl",
                "key": "1b4e28ba-2fa1-41d2-883f-0016d3cca427",
                "curator": "cbro",
                "curator_url": "https://example.org/civil-war",
            },
            {
                "kind": "metron-list",
                "key": "123",
                "url": "https://metron.cloud/reading-list/civil-war/",
            },
        ],
        "previous": {
            "name": "Road to Civil War",
            "kind": "json-cbl",
            "key": "6fa459ea-ee8a-3ca4-894e-db77e160355e",
        },
        "next": {
            "name": "Civil War: The Initiative",
            "kind": "json-cbl",
            "key": "16fd2706-8baf-433b-82eb-8c7fada847da",
        },
    }
    assert {key: result.reading_list[key] for key in expected} == expected


def test_full_document_entries() -> None:
    entries = load(FULL_PATH).reading_list[ENTRIES_KEY]
    assert [entry["entry_type"] for entry in entries] == [
        "core",
        "tie-in",
        "one-shot",
        "ongoing",
    ]
    assert entries[1]["identifiers"] == {
        "comicvine": {"key": "105800"},
        "grandcomicsdatabase": {"key": "311000"},
    }
    assert entries[1]["series"] == {
        "name": "The Amazing Spider-Man",
        "start_year": 1999,
        "identifiers": {
            "comicvine": {"key": "6643"},
            "grandcomicsdatabase": {"key": "8999"},
        },
    }


def test_minimal_document() -> None:
    reading_list = load(MINIMAL_PATH).reading_list
    assert reading_list == {
        "name": "Minimal",
        "ordered": True,
        "sources": [
            {"kind": "json-cbl", "key": "0d3f6c2a-9b1e-4f7a-8c5d-2e6b9a1f4c3d"}
        ],
        ENTRIES_KEY: [
            {
                "series": {"name": "Civil War", "start_year": 2006},
                "issue": {"name": "1"},
                "date": {"cover_date": date(2006, 7, 1)},
            }
        ],
    }


@pytest.mark.parametrize("path", [FULL_PATH, MINIMAL_PATH], ids=lambda path: path.stem)
def test_round_trip(path: Path) -> None:
    reading_list = load(path).reading_list
    assert lost_fields(reading_list, "json-cbl") == ()
    assert loads(dumps(reading_list, "json-cbl")).reading_list == reading_list


def test_detected_by_its_keys() -> None:
    assert detect_format(FULL_PATH.read_text()) is ReadingListFormats.JSON_CBL
    native = dumps(load(MINIMAL_PATH).reading_list, "json")
    assert detect_format(native) is ReadingListFormats.JSON


@pytest.mark.parametrize(
    ("json_cbl", "model"),
    [
        ("team", "teams"),
        ("character", "characters"),
        ("master", "master"),
        ("interuniversal", "interuniversal"),
        ("universal", "universal"),
        ("story", "story"),
    ],
)
def test_list_types_both_ways(json_cbl: str, model: str) -> None:
    document = json.loads(MINIMAL_PATH.read_text())
    document["listDetails"]["type"] = json_cbl
    reading_list = loads(json.dumps(document)).reading_list
    assert reading_list["list_type"] == model
    assert _written(reading_list)["listDetails"]["type"] == json_cbl


def test_event_is_written_as_universal() -> None:
    assert _written(_list(list_type="event"))["listDetails"]["type"] == "universal"


def test_an_unknown_list_type_is_left_out() -> None:
    reading_list = _list(list_type="creator")
    assert "type" not in _written(reading_list)["listDetails"]
    assert lost_fields(reading_list, "json-cbl") == ("list_type",)


@pytest.mark.parametrize(
    ("json_cbl", "model"),
    [
        ("Event Core", "core"),
        ("Event Tie-In", "tie-in"),
        ("Event One Shot", "one-shot"),
        ("Ongoing", "ongoing"),
    ],
)
def test_issue_types_both_ways(json_cbl: str, model: str) -> None:
    document = json.loads(MINIMAL_PATH.read_text())
    document["issueList"][0]["issueType"] = json_cbl
    reading_list = loads(json.dumps(document)).reading_list
    assert reading_list[ENTRIES_KEY][0]["entry_type"] == model
    assert _written(reading_list)["issueList"][0]["issueType"] == json_cbl


def test_an_unknown_entry_type_is_left_out() -> None:
    reading_list = _list(_entry(entry_type="prologue"))
    assert "issueType" not in _written(reading_list)["issueList"][0]
    assert lost_fields(reading_list, "json-cbl") == ("entries.entry_type",)


def test_a_cbl_list_written_as_json_cbl() -> None:
    """A year-only date gets -01-01; an entry with no year is not written."""
    reading_list = load(READING_LISTS_DIR / "cbl" / "common.cbl").reading_list
    reading_list[ENTRIES_KEY].append(
        {"series": {"name": "Civil War", "start_year": 2006}, "issue": {"name": "3"}}
    )
    issues = _written(reading_list)["issueList"]
    assert [issue["issueCoverDate"] for issue in issues] == ["2006-01-01"] * 3
    assert lost_fields(reading_list, "json-cbl") == (
        "entries.volume.number",
        "sources",
        "entries[0, 1, 2].date.cover_date",
        "entries[3]",
    )


def test_a_month_makes_a_better_guess() -> None:
    entry = _entry(date={"year": 2006, "month": 8})
    assert _written(_list(entry))["issueList"][0]["issueCoverDate"] == "2006-08-01"


def test_a_volume_that_is_a_year_is_the_start_year() -> None:
    entry = _entry(series={"name": "Civil War"}, volume={"number": 2006})
    assert _written(_list(entry))["issueList"][0]["seriesStartYear"] == 2006
    entry = _entry(series={"name": "Civil War"}, volume={"number": 1})
    reading_list = _list(entry)
    assert _written(reading_list)["issueList"] == []
    assert "entries[0]" in lost_fields(reading_list, "json-cbl")


def test_an_id_without_its_series_id_is_left_out() -> None:
    entry = _entry(
        series={
            "name": "Civil War",
            "start_year": 2006,
            "identifiers": {"metron": {"key": "1046"}},
        },
        identifiers={"comicvine": {"key": "105747"}, "metron": {"key": "31562"}},
    )
    reading_list = _list(entry)
    assert _written(reading_list)["issueList"][0]["id"] == [
        {"name": "metron", "series": "1046", "issue": "31562"}
    ]
    assert lost_fields(reading_list, "json-cbl") == ("entries.identifiers.comicvine",)


def test_a_relationship_without_a_uuid_is_left_out() -> None:
    reading_list = _list(
        previous={"name": "Road to Civil War"},
        next={"name": "The Initiative", "kind": "json-cbl", "key": "abc"},
    )
    assert _written(reading_list)["listDetails"]["relationships"] == [
        {"name": "The Initiative", "UUID": "abc", "relationship": "following"}
    ]
    assert lost_fields(reading_list, "json-cbl") == ("previous",)


def test_the_uuid_is_kept() -> None:
    reading_list = load(FULL_PATH).reading_list
    written = _written(reading_list)
    assert written["fileDetails"] == {
        "version": 1.0,
        "UUID": "1b4e28ba-2fa1-41d2-883f-0016d3cca427",
    }


def test_a_missing_uuid_is_minted() -> None:
    reading_list = _list()
    first = _written(reading_list)["fileDetails"]["UUID"]
    second = _written(reading_list)["fileDetails"]["UUID"]
    assert uuid.UUID(first).version == 4
    assert first != second


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Marvel Guides", "mg"),
        ("MG", "mg"),
        ("League of Comic Geeks", "locg"),
        ("Some Site", "Some Site"),
    ],
)
def test_curators(name: str, code: str) -> None:
    """A known curator is stored as its code and written back in full."""
    document = json.loads(MINIMAL_PATH.read_text())
    document["listDetails"]["source"] = [{"name": name}]
    reading_list = loads(json.dumps(document)).reading_list
    assert reading_list["sources"][0]["curator"] == code
    written = _written(reading_list)["listDetails"]["source"][0]["name"]
    assert written == CURATORS.get(code, name)


def test_a_newer_major_version_warns() -> None:
    document = json.loads(MINIMAL_PATH.read_text())
    document["fileDetails"]["version"] = 2.0
    assert loads(json.dumps(document)).warnings == (
        "json-cbl version 2.0 read as 1.0.",
    )


def test_private_and_unordered_are_lost() -> None:
    reading_list = _list(private=True, ordered=False)
    assert lost_fields(reading_list, "json-cbl") == ("ordered", "private")
