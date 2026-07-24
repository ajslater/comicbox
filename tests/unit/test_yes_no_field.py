"""Unit tests for ComicInfo's YesNo tags and their boolean comicbox keys."""

from __future__ import annotations

import re

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.enum_fields import ComicInfoMangaField, YesNoField


def _read_tag(tag: str, value: str) -> dict:
    """Parse a minimal ComicInfo.xml carrying one tag."""
    xml = (
        '<?xml version="1.0"?><ComicInfo><Series>S</Series>'
        f"<{tag}>{value}</{tag}></ComicInfo>"
    )
    with Comicbox(metadata=xml, fmt=MetadataFormats.COMIC_INFO) as car:
        return dict(car.to_dict().get("comicbox", {}))


def _write_tag(key: str, value: object, tag: str) -> str | None:
    """Dump a comicbox key to ComicInfo.xml and return the tag's text."""
    md = {"comicbox": {"series": {"name": "S"}, key: value}}
    with Comicbox(metadata=md) as car:
        xml = car.to_string(MetadataFormats.COMIC_INFO)
    match = re.search(rf"<{tag}>(.*?)</{tag}>", xml)
    return match.group(1) if match else None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Yes", True),
        ("No", False),
        ("yes", True),
        ("no", False),
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
    ],
)
def test_black_and_white_reads_as_bool(value: str, expected: bool) -> None:
    """BlackAndWhite parses into the monochrome boolean."""
    assert _read_tag("BlackAndWhite", value)["monochrome"] is expected


def test_black_and_white_unknown_is_no_value() -> None:
    """The schema's Unknown means unrecorded, so monochrome stays absent."""
    assert "monochrome" not in _read_tag("BlackAndWhite", "Unknown")


@pytest.mark.parametrize(("value", "expected"), [(True, "Yes"), (False, "No")])
def test_monochrome_writes_black_and_white(value: bool, expected: str) -> None:
    """Monochrome serializes to the BlackAndWhite tag in both states."""
    assert _write_tag("monochrome", value, "BlackAndWhite") == expected


@pytest.mark.parametrize("value", [True, False])
def test_monochrome_round_trips(value: bool) -> None:
    """Monochrome survives a write then read unchanged."""
    xml = (
        '<?xml version="1.0"?><ComicInfo><Series>S</Series>'
        f"<BlackAndWhite>{'Yes' if value else 'No'}</BlackAndWhite></ComicInfo>"
    )
    with Comicbox(metadata=xml, fmt=MetadataFormats.COMIC_INFO) as car:
        assert car.to_dict()["comicbox"]["monochrome"] is value


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("Yes", True), ("No", False)],
)
def test_yes_no_field_deserializes_bools(value: object, expected: bool) -> None:
    """The field accepts real booleans, not only the Yes & No strings."""
    assert YesNoField().deserialize(value) is expected


@pytest.mark.parametrize(("value", "expected"), [(True, "Yes"), (False, "No")])
def test_yes_no_field_serializes_bools(value: bool, expected: str) -> None:
    """The field renders booleans back to the schema's vocabulary."""
    assert YesNoField()._serialize(value, None, None) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "Yes"), (False, "No"), ("YesAndRightToLeft", "YesAndRightToLeft")],
)
def test_manga_field_handles_bools(value: object, expected: str) -> None:
    """The shared enum-boolean base coerces both boolean states for Manga."""
    field = ComicInfoMangaField()
    assert field.deserialize(value).value == expected
    assert field._serialize(value, None, None) == expected
