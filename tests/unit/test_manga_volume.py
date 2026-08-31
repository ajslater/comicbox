"""MetronInfo MangaVolume is stored verbatim and parsed for convenience."""

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

_METRON_TAGS = (
    "<Series><Name>Foo</Name></Series>",
    "<MangaVolume>{manga_volume}</MangaVolume>",
)


def _read_metron(manga_volume: str) -> dict:
    xml = (
        "<MetronInfo>"
        + "".join(_METRON_TAGS).format(manga_volume=manga_volume)
        + "</MetronInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        return dict(car.to_dict().get("comicbox", {}))


def _write_metron(yaml_str: str) -> str:
    with Comicbox() as car:
        car.add_metadata(yaml_str, MetadataFormats.COMICBOX_YAML)
        return car.to_string(MetadataFormats.METRON_INFO)


@pytest.mark.parametrize(
    ("manga_volume", "number", "number_to"),
    [
        ("3", 3, None),
        ("1-5", 1, 5),
        ("1 - 5", 1, 5),
    ],
)
def test_manga_volume_parses_into_volume(
    manga_volume: str, number: int, number_to: int | None
) -> None:
    """Comicbox reads the numbers out so clients don't have to."""
    sub_md = _read_metron(manga_volume)
    assert sub_md["manga_volume"] == manga_volume
    assert sub_md["volume"]["number"] == number
    assert sub_md["volume"].get("number_to") == number_to


def test_unparsable_manga_volume_is_still_kept() -> None:
    """A string comicbox can't read numbers out of is stored as it was."""
    sub_md = _read_metron("Vol. Omega")
    assert sub_md["manga_volume"] == "Vol. Omega"
    assert not sub_md.get("volume", {}).get("number")


def test_manga_volume_does_not_overwrite_an_explicit_volume() -> None:
    """A Series/Volume the file states wins over the parsed number."""
    xml = (
        "<MetronInfo><Series><Name>Foo</Name><Volume>7</Volume></Series>"
        "<MangaVolume>3</MangaVolume></MetronInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        sub_md = dict(car.to_dict().get("comicbox", {}))
    assert sub_md["volume"]["number"] == 7
    assert sub_md["manga_volume"] == "3"


def test_no_manga_volume_is_fabricated_from_a_volume_number() -> None:
    """
    A western comic must not come out of comicbox claiming a manga volume.

    The volume number used to be rewritten into MangaVolume on every write,
    so every book comicbox touched gained one.
    """
    metron_xml = _write_metron(
        "comicbox:\n  series:\n    name: Captain Science\n  volume:\n    number: 1950\n"
    )
    assert "<Volume>1950</Volume>" in metron_xml
    assert "MangaVolume" not in metron_xml


def test_manga_volume_round_trips() -> None:
    """The value a file supplied is the value written back."""
    metron_xml = _write_metron(
        'comicbox:\n  series:\n    name: Foo\n  manga_volume: "1-5"\n'
    )
    assert "<MangaVolume>1-5</MangaVolume>" in metron_xml
