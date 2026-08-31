"""
ComicInfo's SeriesGroup wrote correctly but never read back.

The tag sat in the transform's name object key map alongside Characters,
Genre, Locations, Tags and Teams, so the read direction turned
``SeriesGroup`` into ``{"G1": {}, "G2": {}}``. Every other member of that
map targets a ``SimpleNamedDictField``, which accepts both a name object
dict and a bare string set; comicbox's ``series_groups`` is a plain
``StringSetField``, which deserializes a Mapping to nothing. The value was
dropped without an error on load. The write direction hid the bug because
the set serialized back to the comma string the tag expects.

SeriesGroup is a string set on both sides, so it belongs in the plain key
map, which passes the set straight through.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any
from zipfile import ZipFile

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.comicbox import SimpleNamedDictField
from comicbox.formats.comet.transform import NAME_OBJ_KEY_MAP as COMET_NAME_OBJ_MAP
from comicbox.formats.comic_book_info.transform import (
    NAME_OBJ_KEYPATHS as CBI_NAME_OBJ_MAP,
)
from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comic_info.transform import (
    NAME_OBJ_KEY_MAP as CIX_NAME_OBJ_MAP,
)
from comicbox.formats.comic_info.transform import ComicInfoTransform
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin, ComicboxSubSchemaMixin
from comicbox.formats.pdf.transform import (
    MUPDF_NAME_OBJ_KEY_MAP,
    XMLPDF_NAME_OBJ_KEY_MAP,
)
from tests.const import EMPTY_CBZ_SOURCE_PATH
from tests.util import get_tmp_dir, my_cleanup, my_setup

_CIX = ComicInfoTransform(None)
_TMP_DIR = get_tmp_dir(__file__)
_TMP_PATH = _TMP_DIR / EMPTY_CBZ_SOURCE_PATH.name

# Every name object key map in the codebase. Their targets must all accept a
# name object dict, which is what `name_obj_to_cb` builds.
_NAME_OBJ_MAPS = MappingProxyType(
    {
        "comic_book_info": CBI_NAME_OBJ_MAP,
        "comet": COMET_NAME_OBJ_MAP,
        "comic_info": CIX_NAME_OBJ_MAP,
        "pdf_mupdf": MUPDF_NAME_OBJ_KEY_MAP,
        "pdf_xml": XMLPDF_NAME_OBJ_KEY_MAP,
    }
)


def _to_cb(native: dict[str, Any]) -> dict:
    loaded: dict = ComicInfoSchema().load({"ComicInfo": native})  # pyright: ignore[reportAssignmentType]
    return dict(_CIX.to_comicbox(loaded).get("comicbox", {}))


def _from_cb(sub_md: dict[str, Any]) -> dict:
    return dict(_CIX.from_comicbox({"comicbox": sub_md}).get("ComicInfo", {}))


def test_series_group_reads() -> None:
    """The tag's comma string becomes the comicbox string set."""
    sub_md = _to_cb({"SeriesGroup": "G1,G2"})
    assert sub_md["series_groups"] == {"G1", "G2"}


def test_series_group_reads_as_a_string_set() -> None:
    """The name object dict it used to build is the shape that got dropped."""
    sub_md = _to_cb({"SeriesGroup": "G1"})
    assert isinstance(sub_md["series_groups"], set)


def test_series_group_writes() -> None:
    """The set still serializes back to the comma string the tag expects."""
    native = _from_cb({"series_groups": {"G2", "G1"}})
    assert native["SeriesGroup"] == {"G1", "G2"}


def test_series_group_round_trips_through_an_archive() -> None:
    """End to end: write ComicInfo.xml into a cbz and read it back."""
    my_setup(_TMP_DIR, EMPTY_CBZ_SOURCE_PATH)
    try:
        cli.main(
            ("comicbox", "-m", "series_groups: [G1, G2]", "-w", "cr", str(_TMP_PATH))
        )
        with ZipFile(_TMP_PATH) as zf:
            xml = zf.read(MetadataFormats.COMIC_INFO.value.filename).decode()
        with Comicbox(_TMP_PATH) as car:
            md = car.to_dict()
    finally:
        my_cleanup(_TMP_DIR)
    assert "<SeriesGroup>G1,G2</SeriesGroup>" in xml
    assert set(md[ComicboxSchemaMixin.ROOT_TAG]["series_groups"]) == {"G1", "G2"}


def test_name_object_maps_only_target_name_object_fields() -> None:
    """A string set field routed through a name object map drops its value."""
    fields = ComicboxSubSchemaMixin().fields
    for format_name, key_map in _NAME_OBJ_MAPS.items():
        for tag, keypath in key_map.items():
            field = fields.get(keypath)
            assert isinstance(field, SimpleNamedDictField), (
                f"{format_name} maps {tag} to {keypath},"
                " which does not accept a name object dict."
            )
