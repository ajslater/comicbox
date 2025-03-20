"""MetronInfo.xml Reprints Transform."""

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import REPRINTS_KEY
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.transforms.transform_map import KeyTransforms
from comicbox.transforms.xml_reprints import filename_to_reprint, reprint_to_filename


def _parse_reprint(source_data, metron_reprint) -> dict:
    """Parse a metron Reprint."""
    comicbox_reprint = {}
    name = get_cdata(metron_reprint)
    if not name:
        return comicbox_reprint
    comicbox_reprint = dict(filename_to_reprint(name))
    metron_id_attribute_to_cb(source_data, "reprint", metron_reprint, comicbox_reprint)
    return comicbox_reprint


def _reprints_to_cb(source_data, metron_reprints):
    return [
        comicbox_reprint
        for metron_reprint in metron_reprints
        if (comicbox_reprint := _parse_reprint(source_data, metron_reprint))
    ]


def _unparse_reprint(source_data, comicbox_reprint) -> dict:
    """Unparse a structured comicbox reprints into metron reprint."""
    metron_reprint = {}
    name = reprint_to_filename(comicbox_reprint)
    if not name:
        return metron_reprint
    metron_reprint["#text"] = name
    metron_id_attribute_from_cb(source_data, metron_reprint, comicbox_reprint)
    return metron_reprint


def _reprints_from_cb(source_data, comicbox_reprints):
    return [
        metron_reprint
        for comicbox_reprint in comicbox_reprints
        if (metron_reprint := _unparse_reprint(source_data, comicbox_reprint))
    ]


METRON_REPRINTS_TRANSFORM = KeyTransforms(
    key_map={"Reprints.Reprint": REPRINTS_KEY},
    to_cb=_reprints_to_cb,
    from_cb=_reprints_from_cb,
)
