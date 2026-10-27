"""
`LanguageField` holds BCP 47 tags.

MetronInfo v1.2 widened `languageCode` from two lowercase letters to a BCP 47
tag. The field used to resolve the whole string through pycountry, so a tag
with a region or script subtag like `pt-BR` was dropped on read and on write.
Now only the primary language subtag goes through pycountry; the rest is kept
and recased per RFC 5646.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.formats.base.fields.pycountry import LanguageField

if TYPE_CHECKING:
    from collections.abc import Iterator

_ATTR = "language"

_VALID = (
    ("en", "en"),
    ("EN", "en"),
    ("eng", "en"),
    ("fil", "fil"),
    ("pt-BR", "pt-BR"),
    ("pt-br", "pt-BR"),
    ("zh-Hant", "zh-Hant"),
    ("ZH-hant-tw", "zh-Hant-TW"),
    ("sr-latn", "sr-Latn"),
    ("es-419", "es-419"),
    ("fr-CA", "fr-CA"),
    ("eng-US", "en-US"),
    ("de-1901", "de-1901"),
    ("az-latn-x-latn", "az-Latn-x-latn"),
    (" en", "en"),
    ("en ", "en"),
    ("English", "en"),
)
_INVALID = ("xx", "qq-BR", "en_US", "pt--br", "en-")


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Collect loguru warning messages."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


@pytest.mark.parametrize(("value", "expected"), _VALID)
def test_deserialize(value: str, expected: str) -> None:
    """Tags are normalized on read."""
    assert LanguageField().deserialize(value, _ATTR) == expected


@pytest.mark.parametrize(("value", "expected"), _VALID)
def test_serialize(value: str, expected: str) -> None:
    """Tags are normalized on write."""
    assert LanguageField().serialize(_ATTR, {_ATTR: value}) == expected


@pytest.mark.parametrize("value", _INVALID)
def test_unknown_or_malformed_is_dropped(value: str, warnings: list[str]) -> None:
    """An unknown primary language or a non-tag pycountry can't name is dropped."""
    field = LanguageField()
    assert field.deserialize(value, _ATTR) == ""
    assert field.serialize(_ATTR, {_ATTR: value}) == ""
    assert any(msg.startswith(f"Couldn't find {_ATTR} for ") for msg in warnings)


def test_single_letter_is_a_language_name() -> None:
    """
    `e` fails the tag pattern but is the name of the language E.

    A value that isn't a tag is looked up whole, the same path that lets
    `English` resolve, so it is kept rather than dropped.
    """
    assert LanguageField().deserialize("e", _ATTR) == "eee"


@pytest.mark.parametrize(
    ("value", "expected"), [("pt-BR", "Portuguese"), ("en", "English")]
)
def test_serialize_name_drops_subtags(value: str, expected: str) -> None:
    """Formats that store a language name get the primary language's name."""
    field = LanguageField(serialize_name=True)
    assert field.serialize(_ATTR, {_ATTR: value}) == expected
