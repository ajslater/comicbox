"""A write that replaces or removes a tag file that did not parse says so (B2)."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.write import write_metadata
from tests.util.comics import make_comic

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_BROKEN = "<{root}><Series>A & B</Series></{root}>"
_TAGS: dict[str, Any] = {"series": "Civil War", "number": "1"}


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handler)


def _write(path: Path, formats: list[str], warnings: list[str]) -> list[str]:
    result = write_metadata(path, {"summary": "x"}, formats=formats)
    assert result.written, result.error
    return [message for message in warnings if "could not be parsed" in message]


def test_a_write_names_the_unparsed_file_it_replaces(
    tmp_path: Path, warnings: list[str]
) -> None:
    """-w cix over a ComicInfo.xml that does not parse replaced it without a word."""
    path = make_comic(
        tmp_path / "broken.cbz",
        files={"ComicInfo.xml": _BROKEN.format(root="ComicInfo")},
        **_TAGS,
    )

    (warning,) = _write(path, ["COMIC_INFO"], warnings)

    assert warning.startswith(f"Replacing ComicInfo.xml in {path}: it could not")
    with zipfile.ZipFile(path) as archive:
        assert "<Series>Civil War</Series>" in archive.read("ComicInfo.xml").decode()


def test_a_write_names_the_unparsed_file_it_removes(
    tmp_path: Path, warnings: list[str]
) -> None:
    path = make_comic(
        tmp_path / "broken.cbz",
        files={"MetronInfo.xml": _BROKEN.format(root="MetronInfo")},
        **_TAGS,
    )

    (warning,) = _write(path, ["COMIC_INFO"], warnings)

    assert warning.startswith(f"Removing MetronInfo.xml from {path}: it could not")


def test_a_write_over_tag_files_that_parse_says_nothing(
    tmp_path: Path, warnings: list[str]
) -> None:
    path = make_comic(tmp_path / "good.cbz", formats=("METRON_INFO",), **_TAGS)
    assert _write(path, ["COMIC_INFO"], warnings) == []
