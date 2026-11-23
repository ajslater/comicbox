"""
MetronInfo v1.3 draft information sources.

The v1.3 draft adds VerseDB to `informationSource`. Marvel has been listed
there since v1.0. `MetronSourceEnum` gates which `<ID source="...">` values
are read and written, so a source missing from it is dropped silently in both
directions. The enum is pinned to the bundled XSD so the next source upstream
adds fails a test instead.
"""

from __future__ import annotations

import pytest
from xmlschema import XMLSchema11
from xmlschema.validators import XsdAtomicRestriction

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.enums.metroninfo import MetronSourceEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.metron_info import REGISTRATION
from comicbox.validate.base import SCHEMA_PATH

_KEY = "1215061"
_SOURCES = pytest.mark.parametrize(
    ("metron_source", "id_source"),
    [("VerseDB", "versedb"), ("Marvel", "marvel")],
)


def test_enum_matches_the_bundled_xsd() -> None:
    """Every schema source is in the enum, and nothing else is."""
    spec = REGISTRATION.validator_spec
    assert spec is not None
    source_type = XMLSchema11(SCHEMA_PATH / spec.schema_path).types["informationSource"]
    assert isinstance(source_type, XsdAtomicRestriction)
    xsd_sources = {str(value) for value in source_type.enumeration or ()}
    assert xsd_sources
    assert {member.value for member in MetronSourceEnum} == xsd_sources


@_SOURCES
def test_id_is_written_to_ids_and_validates(metron_source: str, id_source: str) -> None:
    """The id lands in `<IDS>` and the file passes the v1.3 XSD."""
    yaml = (
        f"comicbox:\n  identifiers:\n    {id_source}:\n"
        f'      key: "{_KEY}"\n  series:\n    name: Foo\n'
    )
    with Comicbox() as car:
        car.add_metadata(yaml, MetadataFormats.COMICBOX_YAML)
        written = car.to_string(MetadataFormats.METRON_INFO)
    assert f'source="{metron_source}">{_KEY}</ID>' in written
    assert "metroninfo/schemas/v1.3" in written
    assert validate_source(written, MetadataFormats.METRON_INFO)


@_SOURCES
def test_id_is_read_from_ids_alone(metron_source: str, id_source: str) -> None:
    """With no `<URLs>` to fall back on, the `<ID>` alone supplies the id."""
    xml = (
        "<MetronInfo><IDS>"
        f'<ID source="{metron_source}" primary="true">{_KEY}</ID>'
        "</IDS></MetronInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        md = car.to_dict()["comicbox"]
    assert md["identifiers"][id_source]["key"] == _KEY
    assert md["primary_id_source"] == id_source
