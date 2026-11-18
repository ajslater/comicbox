"""Comicbox's own reading-list serializations, YAML and JSON."""

from datetime import date

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    ReadingListFormats,
    dumps,
    load,
    loads,
    lost_fields,
)
from comicbox.validate.spec import build_validator
from tests.const import TEST_FILES_DIR

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
CIVIL_WAR_PATH = READING_LISTS_DIR / "civil-war.yaml"
NATIVE_FORMATS = (ReadingListFormats.YAML, ReadingListFormats.JSON)


def test_yaml_fixture_loads() -> None:
    result = load(CIVIL_WAR_PATH)
    assert result.fmt is ReadingListFormats.YAML
    assert result.warnings == ()
    reading_list = result.reading_list
    assert reading_list["name"] == "Civil War"
    assert len(reading_list[ENTRIES_KEY]) == 4
    assert reading_list[ENTRIES_KEY][0]["date"]["cover_date"] == date(2006, 7, 1)


@pytest.mark.parametrize("fmt", NATIVE_FORMATS, ids=lambda fmt: fmt.name)
def test_round_trip(fmt: ReadingListFormats) -> None:
    """YAML loads, dumps to each native format and loads back equal."""
    reading_list = load(CIVIL_WAR_PATH).reading_list
    text = dumps(reading_list, fmt)
    result = loads(text)
    assert result.fmt is fmt
    assert result.reading_list == reading_list
    assert lost_fields(reading_list, fmt) == ()


def test_yaml_dump_is_stable() -> None:
    """Dumping what was read from a dump changes nothing."""
    text = dumps(load(CIVIL_WAR_PATH).reading_list, "yaml")
    assert dumps(loads(text).reading_list, "yaml") == text


def test_yaml_dump_key_order() -> None:
    """Header keys first, entries last; an entry starts with its series."""
    text = dumps(load(CIVIL_WAR_PATH).reading_list, "yaml")
    lines = [
        line for line in text.splitlines() if line.startswith("  ") and line[2] != " "
    ]
    keys = [line.strip().split(":")[0] for line in lines]
    assert keys[0] == "name"
    assert keys[-1] == ENTRIES_KEY
    assert "\n    - series:\n" in text


@pytest.mark.parametrize("fmt", NATIVE_FORMATS, ids=lambda fmt: fmt.name)
def test_dump_validates_against_published_schema(fmt: ReadingListFormats) -> None:
    """What comicbox writes passes the JSON Schema it publishes, dates and all."""
    spec = fmt.value.validator_spec
    assert spec is not None
    build_validator(spec).validate(dumps(load(CIVIL_WAR_PATH).reading_list, fmt))
