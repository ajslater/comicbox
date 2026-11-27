"""
CoMet's cover credit is <coverDesigner>.

CoMetRoleTagEnum.COVER_DESIGNER was the typo "colorDesigner", so the credit
maps never named the schema's coverDesigner field and every cover credit was
dropped on CoMet read and write. The XSD allows one coverDesigner.
"""

from __future__ import annotations

import pytest

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats


def _write_comet(xml: str) -> str:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        return car.to_string(MetadataFormats.COMET)


def test_cover_designer_is_read() -> None:
    """A CoMet coverDesigner loads as a Cover credit."""
    xml = "<comet><title>T</title><coverDesigner>Jane</coverDesigner></comet>"
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMET)
        md = car.to_dict()["comicbox"]
    assert md["credits"] == {"Jane": {"roles": {"Cover": {}}}}


def test_cover_artist_is_written_and_validates() -> None:
    """A ComicInfo CoverArtist becomes a valid CoMet coverDesigner."""
    written = _write_comet(
        "<ComicInfo><Title>T</Title><CoverArtist>A</CoverArtist></ComicInfo>"
    )
    assert "<coverDesigner>A</coverDesigner>" in written
    assert validate_source(written, MetadataFormats.COMET)


@pytest.mark.parametrize("names", ["B,A", "A,B"])
def test_several_cover_artists_write_one_valid_element(names: str) -> None:
    """The XSD allows one coverDesigner, so the first name in sort order is it."""
    written = _write_comet(
        f"<ComicInfo><Title>T</Title><CoverArtist>{names}</CoverArtist></ComicInfo>"
    )
    assert written.count("<coverDesigner>") == 1
    assert "<coverDesigner>A</coverDesigner>" in written
    assert validate_source(written, MetadataFormats.COMET)


def test_cover_designer_round_trips() -> None:
    """CoMet to CoMet keeps the cover credit."""
    xml = "<comet><title>T</title><coverDesigner>Jane</coverDesigner></comet>"
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMET)
        written = car.to_string(MetadataFormats.COMET)
    assert "<coverDesigner>Jane</coverDesigner>" in written
