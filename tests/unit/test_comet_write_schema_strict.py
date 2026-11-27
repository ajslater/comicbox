"""
CoMet writes only what its shipped XSD allows.

CoMet-v1.1.xsd types <issue> as xs:nonNegativeInteger and requires <title>.
The writer copied the issue name verbatim, so "1.5" and "1a" wrote invalid
files, and wrote no title when there was none.
"""

from __future__ import annotations

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats


def _write_comet(xml: str) -> str:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        return car.to_string(MetadataFormats.COMET)


@pytest.mark.parametrize("number", ["1.5", "1a", "-1"])
def test_non_integer_issue_is_left_out(number: str) -> None:
    """An issue the XSD cannot hold is not written, and the file validates."""
    written = _write_comet(
        f"<ComicInfo><Title>T</Title><Number>{number}</Number></ComicInfo>"
    )
    assert "<issue>" not in written
    assert validate_source(written, MetadataFormats.COMET)


@pytest.mark.parametrize("number", ["1", "001", "12"])
def test_integer_issue_is_written(number: str) -> None:
    """A whole issue number is written; issue names are already unpadded."""
    written = _write_comet(
        f"<ComicInfo><Title>T</Title><Number>{number}</Number></ComicInfo>"
    )
    assert f"<issue>{int(number)}</issue>" in written
    assert validate_source(written, MetadataFormats.COMET)


def test_missing_title_warns() -> None:
    """No title is invented, but the incomplete file is reported."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        written = _write_comet("<ComicInfo><Number>1</Number></ComicInfo>")
    finally:
        logger.remove(handler_id)
    assert "<title>" not in written
    assert any("title" in message for message in messages)
