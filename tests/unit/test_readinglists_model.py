"""The reading-list model: schema invariants, detection and errors."""

from typing import Any

import pytest
from marshmallow import Schema

from comicbox.exceptions import ComicboxError
from comicbox.readinglists import (
    ENTRIES_KEY,
    READING_LIST_KEY,
    ReadingListError,
    ReadingListFormatError,
    ReadingListFormats,
    SmartListError,
    detect_format,
    dumps,
    get_format,
    loads,
)
from comicbox.readinglists.formats.cbl.schema import (
    CblBookSchema,
    CblBooksSchema,
    CblDatabaseSchema,
    CblSubSchema,
)
from comicbox.readinglists.schema import (
    EntrySchema,
    JsonEntrySchema,
    ListRefSchema,
    ReadingListJsonSubSchema,
    ReadingListSubSchema,
    SourceSchema,
)

NATIVE_FORMATS = (ReadingListFormats.YAML, ReadingListFormats.JSON)
_CW1 = {
    "series": {"name": "Civil War", "start_year": 2006},
    "issue": {"name": "1"},
}
_ASM = {
    "series": {"name": "Amazing Spider-Man", "start_year": 1999},
    "issue": {"name": "532"},
}


def _reading_list(**header: Any) -> dict[str, Any]:
    return {"name": "Civil War", ENTRIES_KEY: [_CW1, _ASM, _CW1], **header}


@pytest.mark.parametrize(
    "schema_class",
    [
        CblBookSchema,
        CblBooksSchema,
        CblDatabaseSchema,
        CblSubSchema,
        EntrySchema,
        JsonEntrySchema,
        ListRefSchema,
        ReadingListJsonSubSchema,
        ReadingListSubSchema,
        SourceSchema,
    ],
)
def test_tag_order_is_the_field_set(schema_class: type[Schema]) -> None:
    """Dumping drops any key missing from TAG_ORDER, so they must agree."""
    tag_order = schema_class.TAG_ORDER  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
    assert len(tag_order) == len(set(tag_order))
    assert set(tag_order) == set(schema_class().fields)


@pytest.mark.parametrize("fmt", NATIVE_FORMATS, ids=lambda fmt: fmt.name)
def test_dump_keeps_order_and_repeats(fmt: ReadingListFormats) -> None:
    """Entries and sources are never sorted or de-duplicated."""
    sources = [{"kind": "url", "url": "https://b.example"}, {"kind": "file"}] * 2
    reading_list = _reading_list(sources=sources)
    result = loads(dumps(reading_list, fmt)).reading_list
    names = [entry["series"]["name"] for entry in result[ENTRIES_KEY]]
    assert names == ["Civil War", "Amazing Spider-Man", "Civil War"]
    assert result["sources"] == sources


@pytest.mark.parametrize("fmt", NATIVE_FORMATS, ids=lambda fmt: fmt.name)
def test_false_flags_survive(fmt: ReadingListFormats) -> None:
    result = loads(dumps(_reading_list(ordered=False, private=False), fmt))
    assert result.reading_list["ordered"] is False
    assert result.reading_list["private"] is False


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("list_type", "Event", "event"),
        ("list_type", "TEAMS", "teams"),
        ("list_type", "team", "teams"),
        ("list_type", "Character", "characters"),
        ("list_type", "Interuniversal", "interuniversal"),
        ("entry_type", "Tie In", "tie-in"),
        ("entry_type", "TIE_IN", "tie-in"),
        ("entry_type", "Core", "core"),
        ("entry_type", "Something New", "something-new"),
    ],
)
def test_vocabulary_fields(field: str, value: str, expected: str) -> None:
    """Known synonyms map to one spelling; unknown values pass through."""
    if field == "list_type":
        reading_list = _reading_list(list_type=value)
        result = loads(dumps(reading_list, "yaml")).reading_list
        assert result["list_type"] == expected
    else:
        entry = {**_CW1, "entry_type": value}
        result = loads(dumps(_reading_list(entries=[entry]), "yaml")).reading_list
        assert result[ENTRIES_KEY][0]["entry_type"] == expected


_YAML = "reading_list:\n  name: A\n"
_JSON = '{"reading_list": {"name": "A"}}'


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_YAML, ReadingListFormats.YAML),
        (_YAML.encode(), ReadingListFormats.YAML),
        ("﻿" + _YAML, ReadingListFormats.YAML),
        (_JSON, ReadingListFormats.JSON),
        (_JSON.encode("utf-8-sig"), ReadingListFormats.JSON),
        ("", None),
        ("   \n", None),
        ("junk", None),
        ("{not json", None),
        ("[1, 2]", None),
        ('{"comicbox": {"series": {"name": "A"}}}', None),
        ("comicbox:\n  series: A\n", None),
        ("key: [unclosed", None),
        ('<?xml version="1.0"?>\n<ComicInfo><Series>A</Series></ComicInfo>', None),
    ],
    ids=[
        "yaml",
        "yaml-bytes",
        "yaml-bom",
        "json",
        "json-bom-bytes",
        "empty",
        "blank",
        "junk",
        "broken-json",
        "json-list",
        "json-comic",
        "yaml-comic",
        "broken-yaml",
        "xml-comic",
    ],
)
def test_detect_format(data: str | bytes, expected: ReadingListFormats | None) -> None:
    assert detect_format(data) is expected


@pytest.mark.parametrize(
    ("data", "fmt"),
    [
        ("comicbox:\n  series: A\n", None),
        ("comicbox:\n  series: A\n", "yaml"),
        ('{"comicbox": {}}', "json"),
        ("reading_list: {}\n", "yaml"),
        ('{"reading_list": {"bogus": 1}}', None),
        ("key: [unclosed", "yaml"),
        ("", None),
    ],
    ids=[
        "no-root-detected",
        "no-root-yaml",
        "no-root-json",
        "empty-root",
        "nothing-readable",
        "unparsable",
        "empty",
    ],
)
def test_not_a_reading_list_raises(data: str, fmt: str | None) -> None:
    with pytest.raises(ReadingListFormatError):
        loads(data, fmt=fmt)


def test_format_tokens() -> None:
    assert get_format("YAML") is ReadingListFormats.YAML
    assert get_format(ReadingListFormats.JSON) is ReadingListFormats.JSON
    with pytest.raises(ReadingListFormatError, match="Known formats"):
        get_format("cbr")


def test_dumps_accepts_the_wrapped_form() -> None:
    reading_list = _reading_list()
    assert dumps({READING_LIST_KEY: reading_list}, "json") == dumps(
        reading_list, "json"
    )


def test_dumps_refuses_an_empty_list() -> None:
    with pytest.raises(ReadingListFormatError):
        dumps({"bogus": 1}, "yaml")


def test_exception_hierarchy() -> None:
    assert issubclass(ReadingListError, ComicboxError)
    assert issubclass(ReadingListFormatError, ReadingListError)
    assert issubclass(SmartListError, ReadingListFormatError)
