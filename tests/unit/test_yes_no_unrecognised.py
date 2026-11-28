"""
An unrecognised Manga or BlackAndWhite value is dropped with a warning.

`EnumBooleanField._coerce_bool` read anything that was neither an enum
spelling nor `1`/`true`/`yes` as No, silently. Garbage or a near miss
(`maybe`, `Y`, `Yes (RTL)`) became an asserted "not manga" or "not black and
white", which then won merges and was written back as `<Manga>No</Manga>`.
Only known spellings map now; anything else falls through to the enum field
so the error store logs the drop.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.enums.comicbox import MangaEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.enum_fields import (
    ComicInfoMangaEnum,
    ComicInfoMangaField,
    MangaField,
    YesNoField,
)
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

if TYPE_CHECKING:
    from collections.abc import Iterator

_UNRECOGNISED = ("maybe", "Yes (RTL)", "2", "-1", "on", "off", "nope")


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Capture WARNING records."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handler_id)


def _read_cix(tag: str, value: str) -> tuple[dict, str]:
    xml = (
        '<?xml version="1.0"?><ComicInfo><Series>S</Series>'
        f"<{tag}>{value}</{tag}></ComicInfo>"
    )
    with Comicbox(metadata=xml, fmt=MetadataFormats.COMIC_INFO) as car:
        md = dict(car.to_dict().get("comicbox", {}))
        written = car.to_string(MetadataFormats.COMIC_INFO)
    return md, written


def _load_manga(value: object) -> dict:
    loaded = ComicboxYamlSchema().load({"comicbox": {"manga": value}})
    assert isinstance(loaded, Mapping)
    return dict(loaded.get("comicbox", {}))


@pytest.mark.parametrize("value", _UNRECOGNISED)
def test_comicinfo_manga_unrecognised_is_dropped(
    value: str, warnings: list[str]
) -> None:
    """ComicInfo Manga: no value, a logged drop, and no <Manga> written back."""
    md, written = _read_cix("Manga", value)
    assert "manga" not in md
    assert any("Dropped invalid metadata" in w and "Manga" in w for w in warnings)
    assert "<Manga>" not in written


@pytest.mark.parametrize("value", _UNRECOGNISED)
def test_comicinfo_black_and_white_unrecognised_is_dropped(
    value: str, warnings: list[str]
) -> None:
    """ComicInfo BlackAndWhite: no monochrome, a logged drop, nothing written."""
    md, written = _read_cix("BlackAndWhite", value)
    assert "monochrome" not in md
    assert any("BlackAndWhite" in w for w in warnings)
    assert "<BlackAndWhite>" not in written


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("y", True),
        ("Y", True),
        ("n", False),
        ("N", False),
        (" true ", True),
        (" No ", False),
        ("FALSE", False),
    ],
)
def test_comicinfo_black_and_white_known_spellings(
    value: str, expected: bool, warnings: list[str]
) -> None:
    """The short and padded spellings read, case and whitespace ignored."""
    md, _ = _read_cix("BlackAndWhite", value)
    assert md["monochrome"] is expected
    assert not warnings


@pytest.mark.parametrize(
    ("value", "expected"),
    [("y", MangaEnum.YES), ("n", MangaEnum.NO), (" 1 ", MangaEnum.YES)],
)
def test_comicinfo_manga_known_spellings(
    value: str, expected: MangaEnum, warnings: list[str]
) -> None:
    """ComicInfo Manga reads y and n."""
    md, _ = _read_cix("Manga", value)
    assert md["manga"] == expected.value
    assert not warnings


def test_comicinfo_manga_right_to_left_unchanged(warnings: list[str]) -> None:
    """Manga's right-to-left value reads as today."""
    md, written = _read_cix("Manga", "YesAndRightToLeft")
    assert md["manga"] == MangaEnum.YES.value
    assert "<Manga>YesAndRightToLeft</Manga>" in written
    assert not warnings


@pytest.mark.parametrize("value", [*_UNRECOGNISED, pytest.param(2, id="int-2")])
def test_comicbox_manga_unrecognised_is_dropped(
    value: object, warnings: list[str]
) -> None:
    """Comicbox YAML/JSON manga drops garbage with a warning."""
    assert "manga" not in _load_manga(value)
    assert len(warnings) == 1
    assert "manga" in warnings[0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, MangaEnum.YES),
        (False, MangaEnum.NO),
        (1, MangaEnum.YES),
        (0, MangaEnum.NO),
        ("y", MangaEnum.YES),
        ("n", MangaEnum.NO),
        ("Unknown", MangaEnum.UNKNOWN),
    ],
)
def test_comicbox_manga_known_spellings(
    value: object, expected: MangaEnum, warnings: list[str]
) -> None:
    """Bools, 0/1, y/n and the enum's own spellings still read."""
    assert _load_manga(value)["manga"] == expected
    assert not warnings


def test_unrecognised_value_writes_no_tag() -> None:
    """Dumping a value no spelling matches writes nothing instead of No."""
    assert ComicInfoMangaField()._serialize("maybe", None, None) is None
    assert MangaField()._serialize("maybe", None, None) is None
    assert YesNoField()._serialize("maybe", None, None) is None
    assert ComicInfoMangaField().serialize("v", {"v": True}) == "Yes"
    assert ComicInfoMangaField()._serialize("n", None, None) == "No"


def test_comicbox_metadata_with_garbage_manga_writes_no_comicinfo_tag() -> None:
    """End to end: comicbox metadata with manga 'maybe' writes no <Manga>."""
    md = {"comicbox": {"series": {"name": "S"}, "manga": "maybe"}}
    with Comicbox(metadata=md) as car:
        xml = car.to_string(MetadataFormats.COMIC_INFO)
    assert not re.search(r"<Manga>", xml)


def test_enum_spellings_are_untouched() -> None:
    """Every enum member's own value still reads as that member."""
    field = ComicInfoMangaField()
    for member in ComicInfoMangaEnum:
        assert field.deserialize(member.value) == member
