"""
Reprints and series alternative names are separate concepts.

A reprint is another edition of this issue's content. An alternative name is
another name the same series goes by. MetronInfo keeps them in different
tags; comicbox used to merge both into `reprints` and then write that one
list back out to both tags, which multiplied entries on every round trip.
"""

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

_METRON_XML = """<MetronInfo>
  <Series>
    <Name>Captain Science</Name>
    <AlternativeNames>
      <AlternativeName lang="es">Capitán Ciencia</AlternativeName>
      <AlternativeName>Captain Science Alternate</AlternativeName>
    </AlternativeNames>
  </Series>
  <Reprints>
    <Reprint>Strange Academy (2020) #1</Reprint>
  </Reprints>
</MetronInfo>"""


def _read(xml: str) -> dict:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        return dict(car.to_dict().get("comicbox", {}))


def _round_trip(xml: str) -> str:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        return car.to_string(MetadataFormats.METRON_INFO)


def test_alternative_names_are_not_reprints() -> None:
    """Each tag lands in its own field."""
    sub_md = _read(_METRON_XML)
    assert sub_md["series"]["alternative_names"] == [
        {"name": "Captain Science Alternate"},
        {"language": "es", "name": "Capitán Ciencia"},
    ]
    assert [reprint["name"] for reprint in sub_md["reprints"]] == [
        "Strange Academy (2020) #1"
    ]


def test_a_name_with_no_language_still_reads() -> None:
    """
    Lang defaults to en in the schema.

    An AlternativeName written without attributes parses as a bare string
    rather than a mapping, and used to be dropped entirely.
    """
    sub_md = _read(_METRON_XML)
    names = [name["name"] for name in sub_md["series"]["alternative_names"]]
    assert "Captain Science Alternate" in names


def test_round_trip_does_not_multiply_entries() -> None:
    """One reprint and two alternative names stay one and two."""
    written = _round_trip(_METRON_XML)
    assert written.count("<Reprint>") == 1
    assert written.count("</AlternativeName>") == 2


def test_reprint_name_is_kept_verbatim() -> None:
    """A name no filename grammar models survives unchanged."""
    xml = (
        "<MetronInfo><Series><Name>Foo</Name></Series><Reprints>"
        "<Reprint>Amazing Fantasy #15 (2nd printing)</Reprint>"
        "</Reprints></MetronInfo>"
    )
    assert _read(xml)["reprints"][0]["name"] == "Amazing Fantasy #15 (2nd printing)"
    assert "Amazing Fantasy #15 (2nd printing)" in _round_trip(xml)


def test_reprint_name_is_parsed_for_convenience() -> None:
    """Comicbox reads the series and issue out of the name for clients."""
    reprint = _read(_METRON_XML)["reprints"][0]
    assert reprint["series"]["name"] == "Strange Academy"
    assert reprint["issue"] == "1"


def test_an_empty_alternative_name_is_ignored() -> None:
    """An empty element names nothing."""
    xml = (
        "<MetronInfo><Series><Name>Foo</Name><AlternativeNames>"
        "<AlternativeName/><AlternativeName>Bar</AlternativeName>"
        "</AlternativeNames></Series></MetronInfo>"
    )
    assert _read(xml)["series"]["alternative_names"] == [{"name": "Bar"}]
