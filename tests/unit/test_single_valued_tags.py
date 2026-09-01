"""Tags their own spec defines as single-valued are not split into sets."""

from typing import Any

import pytest

from comicbox.formats.comet.schema import CoMetSchema
from comicbox.formats.comet.transform import CoMetTransform
from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comic_info.transform import ComicInfoTransform

_CIX = ComicInfoTransform(None)
_COMET = CoMetTransform(None)


def _cix_to_cb(native: dict[str, Any]) -> dict:
    """Load through the schema first, the way the read pipeline does."""
    loaded: dict = ComicInfoSchema().load({"ComicInfo": native})  # pyright: ignore[reportAssignmentType]
    return dict(_CIX.to_comicbox(loaded).get("comicbox", {}))


def _cix_from_cb(sub_md: dict[str, Any]) -> dict:
    return dict(_CIX.from_comicbox({"comicbox": sub_md}).get("ComicInfo", {}))


def _comet_to_cb(native: dict[str, Any]) -> dict:
    loaded: dict = CoMetSchema().load({"comet": native})  # pyright: ignore[reportAssignmentType]
    return dict(_COMET.to_comicbox(loaded).get("comicbox", {}))


def _comet_from_cb(sub_md: dict[str, Any]) -> dict:
    return dict(_COMET.from_comicbox({"comicbox": sub_md}).get("comet", {}))


def test_main_character_or_team_is_one_name() -> None:
    """A protagonist with a comma in their name is not two characters."""
    sub_md = _cix_to_cb({"MainCharacterOrTeam": "Hank McCoy, Beast"})
    assert sub_md["protagonist"] == "Hank McCoy, Beast"


@pytest.mark.parametrize(
    ("gtin", "id_source", "key"),
    [
        # 13 digits reads as an ISBN, other lengths as a UPC.
        ("9781234567890", "isbn", "9781234567890"),
        ("978-1-234-56789-0", "isbn", "978-1-234-56789-0"),
        ("76194130593600111", "upc", "76194130593600111"),
    ],
)
def test_gtin_reads_as_a_barcode(gtin: str, id_source: str, key: str) -> None:
    """GTIN is a barcode, which is what other readers expect there."""
    identifiers = _cix_to_cb({"GTIN": gtin})["identifiers"]
    assert identifiers[id_source]["key"] == key


def test_gtin_still_reads_urns_comicbox_used_to_write() -> None:
    """Files an older comicbox wrote carry a comma-joined urn list."""
    identifiers = _cix_to_cb(
        {"GTIN": "urn:comicvine:issue:145269,urn:metron:issue:99999"}
    )["identifiers"]
    assert identifiers["comicvine"]["key"] == "145269"
    assert identifiers["metron"]["key"] == "99999"


def test_gtin_writes_only_a_barcode() -> None:
    """A database id must not be written into the barcode field."""
    comicinfo = _cix_from_cb(
        {
            "identifiers": {
                "comicvine": {"key": "145269"},
                "isbn": {"key": "9781234567890"},
            }
        }
    )
    assert comicinfo["GTIN"] == "9781234567890"


def test_gtin_is_absent_without_a_barcode() -> None:
    """No barcode, no GTIN — not a urn standing in for one."""
    comicinfo = _cix_from_cb({"identifiers": {"comicvine": {"key": "145269"}}})
    assert not comicinfo.get("GTIN")


def test_translator_splits_like_the_other_creator_tags() -> None:
    """ComicRack's comma convention covers Translator too."""
    sub_md = _cix_to_cb({"Translator": "Ana Lopez, Bo Chen"})
    assert set(sub_md["credits"]) == {"Ana Lopez", "Bo Chen"}


def test_comet_identifier_is_one_value() -> None:
    """CoMet's identifier is maxOccurs=1, so it is read whole."""
    sub_md = _comet_to_cb({"identifier": "urn:comicvine:issue:145269"})
    assert sub_md["identifiers"]["comicvine"]["key"] == "145269"


def test_comet_identifier_writes_the_best_ranked_source() -> None:
    """
    One tag, many ids: the best ranked source wins.

    Rank is IdSources declaration order, where metron precedes comicvine.
    """
    comet = _comet_from_cb(
        {
            "identifiers": {
                "comicvine": {"key": "145269", "id_type": "issue"},
                "metron": {"key": "99999", "id_type": "issue"},
            }
        }
    )
    # The issue type is the default, so the urn leaves it implicit.
    assert comet["identifier"] == "urn:metron:99999"


def test_comet_is_version_of_is_one_value() -> None:
    """CoMet's isVersionOf is maxOccurs=1, so it is one reprint."""
    sub_md = _comet_to_cb({"isVersionOf": "Captain Science Alternate #001"})
    reprints = sub_md["reprints"]
    assert len(reprints) == 1
    assert reprints[0]["series"]["name"] == "Captain Science Alternate"
