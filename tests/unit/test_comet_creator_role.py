"""
A generic CoMet <creator> is MetronInfo role Other.

The MetronInfo role aliases mapped CoMet's creator to Chief Creative
Officer, a corporate title, so converting any CoMet creator credit to
MetronInfo claimed that title for them.
"""

from __future__ import annotations

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats


def _convert(xml: str, src: MetadataFormats, dest: MetadataFormats) -> str:
    with Comicbox() as car:
        car.add_metadata(xml, src)
        return car.to_string(dest)


def test_comet_creator_is_metron_other() -> None:
    """A CoMet creator converts to a valid MetronInfo Other credit."""
    written = _convert(
        "<comet><title>T</title><series>S</series><creator>Stan</creator></comet>",
        MetadataFormats.COMET,
        MetadataFormats.METRON_INFO,
    )
    assert "<Role>Other</Role>" in written
    assert "Chief Creative Officer" not in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


def test_metron_chief_creative_officer_round_trips() -> None:
    """A real MetronInfo Chief Creative Officer credit stays one."""
    xml = (
        "<MetronInfo><Series><Name>S</Name></Series>"
        "<Credits><Credit><Creator>Joe</Creator>"
        "<Roles><Role>Chief Creative Officer</Role></Roles>"
        "</Credit></Credits></MetronInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        md = car.to_dict()["comicbox"]
        written = car.to_string(MetadataFormats.METRON_INFO)
    assert md["credits"] == {"Joe": {"roles": {"Chief Creative Officer": {}}}}
    assert "<Role>Chief Creative Officer</Role>" in written


def test_metron_other_is_not_comet_creator() -> None:
    """MetronInfo Other has no CoMet tag; it does not become a creator."""
    written = _convert(
        "<MetronInfo><Series><Name>S</Name></Series><Stories><Story>T</Story></Stories>"
        "<Credits><Credit><Creator>Stan</Creator>"
        "<Roles><Role>Other</Role></Roles>"
        "</Credit></Credits></MetronInfo>",
        MetadataFormats.METRON_INFO,
        MetadataFormats.COMET,
    )
    assert "<creator>" not in written
