"""MetronInfo.xml Reprints Transform."""

from comicfn2dict.parse import comicfn2dict
from comicfn2dict.unparse import dict2comicfn
from glom import glom

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox import (
    LANGUAGE_KEY,
    NAME_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
)
from comicbox.schemas.metroninfo import ALTERNATIVE_NAMES_TAGPATH, LANG_ATTR
from comicbox.transforms.identifiers import PRIMARY_ID_SOURCE_KEYPATH
from comicbox.transforms.metroninfo.const import DEFAULT_ID_SOURCE
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.transforms.metroninfo.identifiers import SCOPE_PRIMARY_SOURCE
from comicbox.transforms.spec import MetaSpec
from comicbox.transforms.xml_reprints import (
    FILENAME_TO_REPRINT_SPECS,
    REPRINT_TO_FILENAME_SPECS,
)

REPRINTS_TAGPATH = "Reprints.Reprint"


def _reprint_to_cb(metron_reprint, primary_id_source) -> dict:
    """Parse a metron Reprint."""
    comicbox_reprint = {}
    if name := get_cdata(metron_reprint):
        filename_dict = comicfn2dict(str(name))
        comicbox_reprint = glom(filename_dict, dict(FILENAME_TO_REPRINT_SPECS))
        metron_id_attribute_to_cb(
            "reprint", metron_reprint, comicbox_reprint, primary_id_source
        )
    return comicbox_reprint


def _alternative_name_to_cb(metron_alternative_name, primary_id_source):
    comicbox_reprint = {}
    if not metron_alternative_name:
        return comicbox_reprint
    if alternative_name := get_cdata(metron_alternative_name):
        comicbox_reprint[SERIES_KEY] = {NAME_KEY: alternative_name}
    if alternative_name_lang := metron_alternative_name.get(LANG_ATTR):
        comicbox_reprint[LANGUAGE_KEY] = alternative_name_lang

    metron_id_attribute_to_cb(
        "reprint", metron_alternative_name, comicbox_reprint, primary_id_source
    )
    return comicbox_reprint


def _reprints_to_cb(values):
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    if metron_reprints := values.get(REPRINTS_TAGPATH):
        comicbox_reprints = [
            comicbox_reprint
            for metron_reprint in metron_reprints
            if (comicbox_reprint := _reprint_to_cb(metron_reprint, primary_id_source))
        ]
    else:
        comicbox_reprints = []
    if metron_alternative_names := values.get(ALTERNATIVE_NAMES_TAGPATH):
        an_comicbox_reprints = [
            comicbox_reprint
            for metron_alternative_name in metron_alternative_names
            if (
                comicbox_reprint := _alternative_name_to_cb(
                    metron_alternative_name, primary_id_source
                )
            )
        ]
        comicbox_reprints.extend(an_comicbox_reprints)
    return comicbox_reprints


def _reprint_from_cb(comicbox_reprint, primary_id_source) -> dict:
    """Unparse a structured comicbox reprints into metron reprint."""
    filename_dict = glom(comicbox_reprint, dict(REPRINT_TO_FILENAME_SPECS))
    name = dict2comicfn(filename_dict, ext=False)
    metron_reprint = {}
    if not name:
        return metron_reprint
    metron_reprint["#text"] = name
    metron_id_attribute_from_cb(metron_reprint, comicbox_reprint, primary_id_source)
    return metron_reprint


def _reprints_from_cb(values):
    comicbox_reprints = values.get(REPRINTS_KEY)
    if not comicbox_reprints:
        return []
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    return [
        metron_reprint
        for comicbox_reprint in comicbox_reprints
        if (metron_reprint := _reprint_from_cb(comicbox_reprint, primary_id_source))
    ]


METRON_REPRINTS_TRANSFORM_TO_CB = MetaSpec(
    key_map={
        REPRINTS_KEY: (
            REPRINTS_TAGPATH,
            ALTERNATIVE_NAMES_TAGPATH,
            SCOPE_PRIMARY_SOURCE,
        )
    },
    spec=_reprints_to_cb,
)
METRON_REPRINTS_TRANSFORM_FROM_CB = MetaSpec(
    key_map={REPRINTS_TAGPATH: (REPRINTS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_reprints_from_cb,
)
