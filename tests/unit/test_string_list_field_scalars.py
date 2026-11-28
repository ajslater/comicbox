"""
String list and set fields read a bare number and refuse a mapping visibly.

`StringListField._deserialize` only handled strings and collections, so a
YAML `tags: 1984` returned an empty list without raising and the error store
never logged it: the tag vanished. In the other direction every collection
item was `str()`ed, so a mapping inside `genres` became a genre named
`{'x': 1}`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import pytest
from loguru import logger
from marshmallow import ValidationError

from comicbox.formats.base.fields.collection_fields import (
    StringListField,
    StringSetField,
)
from comicbox.formats.base.fields.xml_fields import XmlStringSetField
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Capture WARNING records."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handler_id)


def _load(key: str, value: object) -> dict:
    loaded = ComicboxYamlSchema().load({"comicbox": {key: value}})
    assert isinstance(loaded, Mapping)
    return dict(loaded.get("comicbox", {}))


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("tags", 5, {"5": {}}),
        ("stories", 1984, {"1984": {}}),
        ("genres", 1.5, {"1.5": {}}),
        ("tags", 0, {"0": {}}),
    ],
)
def test_a_bare_number_names_one_item(
    key: str, value: object, expected: dict, warnings: list[str]
) -> None:
    """A number is a perfectly good tag, genre or story name."""
    assert _load(key, value)[key] == expected
    assert not warnings


def test_a_bare_number_series_group(warnings: list[str]) -> None:
    """The plain set field reads a number too."""
    assert _load("series_groups", 52)["series_groups"] == {"52"}
    assert not warnings


@pytest.mark.parametrize(
    ("key", "value"),
    [("tags", True), ("series_groups", {"a": 1}), ("series_groups", False)],
)
def test_an_unreadable_scalar_is_dropped_with_a_warning(
    key: str, value: object, warnings: list[str]
) -> None:
    """A bool or mapping where a list of names belongs is logged, not lost."""
    assert key not in _load(key, value)
    assert len(warnings) == 1
    assert "Dropped invalid metadata" in warnings[0]
    assert key in warnings[0]


def test_a_mapping_item_is_not_a_name(warnings: list[str]) -> None:
    """A dict inside genres never becomes a genre named after its repr."""
    loaded = _load("genres", [1, {"x": 1}])
    assert "{'x': 1}" not in loaded.get("genres", {})
    assert len(warnings) == 1
    assert "genres" in warnings[0]


def test_a_mapping_item_in_a_plain_set_field(warnings: list[str]) -> None:
    """The set field refuses a mapping item, dropping the field with a warning."""
    with pytest.raises(ValidationError):
        StringSetField().deserialize([1, {"x": 1}])
    assert "series_groups" not in _load("series_groups", [1, {"x": 1}])
    assert len(warnings) == 1
    assert "series_groups" in warnings[0]


def test_a_string_still_splits() -> None:
    """CSV strings and lists are read as before."""
    field = StringListField()
    assert field.deserialize("a, b;c") == ["a", "b", "c"]
    assert field.deserialize(["a", 2]) == ["a", "2"]


def test_an_attributed_xml_item_reads_its_text() -> None:
    """An XML element with attributes is unwrapped, not stringified."""
    field = XmlStringSetField()
    assert field.deserialize([{"@lang": "en", "#text": "Horror"}, "Drama"]) == {
        "Horror",
        "Drama",
    }
