"""
MetronInfo v1.2 language tags survive a round trip.

`Series@lang` and `AlternativeName@lang` are BCP 47 tags in v1.2. Region and
script subtags used to be dropped on read, so writing the file back lost them.
"""

from comicbox.box import Comicbox
from comicbox.box.validate import validate_source
from comicbox.formats import MetadataFormats

_METRON_XML = """<MetronInfo>
  <Series lang="pt-br">
    <Name>Capitão Ciência</Name>
    <AlternativeNames>
      <AlternativeName lang="zh-hant">科學隊長</AlternativeName>
    </AlternativeNames>
  </Series>
</MetronInfo>"""


def test_read_keeps_subtags() -> None:
    """Tags read whole and recased."""
    with Comicbox() as car:
        car.add_metadata(_METRON_XML, MetadataFormats.METRON_INFO)
        sub_md = car.to_dict()["comicbox"]
    assert sub_md["language"] == "pt-BR"
    assert sub_md["series"]["alternative_names"] == [
        {"language": "zh-Hant", "name": "科學隊長"}
    ]


def test_write_keeps_subtags_and_validates() -> None:
    """The written file carries the full tags and passes the v1.2 XSD."""
    with Comicbox() as car:
        car.add_metadata(_METRON_XML, MetadataFormats.METRON_INFO)
        written = car.to_string(MetadataFormats.METRON_INFO)
    assert 'lang="pt-BR"' in written
    assert 'lang="zh-Hant"' in written
    assert "metroninfo/schemas/v1.2" in written
    assert validate_source(written, MetadataFormats.METRON_INFO)
