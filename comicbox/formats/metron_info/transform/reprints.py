"""
MetronInfo.xml Reprints Transform.

A Reprint names another edition of this issue's content. Its name is free
text — "Strange Academy (2020) #1" is the shape Metron publishes, but nothing
guarantees it — so comicbox stores what the file said and writes that back.
The structured series/volume/issue fields are read out of the name in the
computed layer as a convenience, never as the authority.

Series/AlternativeNames is a different concept and lives on the series now.
It used to be appended to reprints and then written back out to both tags,
which multiplied entries on every round trip.
"""

from collections.abc import Mapping
from typing import Any

from comicfn2dict.unparse import dict2comicfn
from glom import glom

from comicbox.formats.base.fields.xml_fields import get_cdata
from comicbox.formats.base.transforms.identifiers import PRIMARY_ID_SOURCE_KEYPATH
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.base.transforms.xml_reprints import REPRINT_TO_FILENAME_SPECS
from comicbox.formats.comicbox.schema import (
    ALTERNATIVE_NAMES_KEYPATH,
    LANGUAGE_KEY,
    NAME_KEY,
    REPRINTS_KEY,
)
from comicbox.formats.metron_info.schema import ALTERNATIVE_NAMES_TAGPATH, LANG_ATTR
from comicbox.formats.metron_info.transform.const import DEFAULT_ID_SOURCE
from comicbox.formats.metron_info.transform.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.formats.metron_info.transform.identifiers import SCOPE_PRIMARY_SOURCE

REPRINTS_TAGPATH = "Reprints.Reprint"


def _reprint_to_cb(
    metron_reprint: dict[str, str] | str, primary_id_source: str
) -> dict:
    """Keep the reprint's name as the file wrote it."""
    comicbox_reprint: dict[str, Any] = {}
    if name := get_cdata(metron_reprint):
        comicbox_reprint[NAME_KEY] = str(name)
        metron_id_attribute_to_cb(
            "reprint", metron_reprint, comicbox_reprint, primary_id_source
        )
    return comicbox_reprint


def _reprints_to_cb(values: dict[str, Any]) -> list:
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    metron_reprints = values.get(REPRINTS_TAGPATH) or ()
    return [
        comicbox_reprint
        for metron_reprint in metron_reprints
        if (comicbox_reprint := _reprint_to_cb(metron_reprint, primary_id_source))
    ]


def _reprint_from_cb(comicbox_reprint: dict[str, Any], primary_id_source: str) -> dict:
    """Write the stored name, or build one when a reprint has none."""
    name = comicbox_reprint.get(NAME_KEY)
    if not name:
        filename_dict = glom(comicbox_reprint, dict(REPRINT_TO_FILENAME_SPECS))
        name = dict2comicfn(filename_dict, ext=False)
    metron_reprint = {}
    if not name:
        return metron_reprint
    metron_reprint["#text"] = name
    metron_id_attribute_from_cb(metron_reprint, comicbox_reprint, primary_id_source)
    return metron_reprint


def _reprints_from_cb(values: dict[str, Any]) -> list:
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
    key_map={REPRINTS_KEY: (REPRINTS_TAGPATH, SCOPE_PRIMARY_SOURCE)},
    spec=_reprints_to_cb,
)
METRON_REPRINTS_TRANSFORM_FROM_CB = MetaSpec(
    key_map={REPRINTS_TAGPATH: (REPRINTS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_reprints_from_cb,
)


def _alternative_name_to_cb(
    metron_alternative_name: Mapping[str, str] | str, primary_id_source: str
) -> dict:
    comicbox_alternative_name: dict[str, Any] = {}
    if not metron_alternative_name:
        return comicbox_alternative_name
    if name := get_cdata(metron_alternative_name):
        comicbox_alternative_name[NAME_KEY] = str(name)
    # An AlternativeName with no attributes parses as a bare string.
    if not isinstance(metron_alternative_name, Mapping):
        return comicbox_alternative_name
    if lang := metron_alternative_name.get(LANG_ATTR):
        comicbox_alternative_name[LANGUAGE_KEY] = lang
    metron_id_attribute_to_cb(
        "series", metron_alternative_name, comicbox_alternative_name, primary_id_source
    )
    return comicbox_alternative_name


def _alternative_names_to_cb(values: dict[str, Any]) -> list:
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    metron_alternative_names = values.get(ALTERNATIVE_NAMES_TAGPATH) or ()
    return [
        comicbox_alternative_name
        for metron_alternative_name in metron_alternative_names
        if (
            comicbox_alternative_name := _alternative_name_to_cb(
                metron_alternative_name, primary_id_source
            )
        )
    ]


def _alternative_names_from_cb(values: dict[str, Any]) -> list:
    comicbox_alternative_names = values.get(ALTERNATIVE_NAMES_KEYPATH)
    if not comicbox_alternative_names:
        return []
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    metron_alternative_names = []
    for comicbox_alternative_name in comicbox_alternative_names:
        name = comicbox_alternative_name.get(NAME_KEY)
        if not name:
            continue
        metron_alternative_name: dict[str, Any] = {"#text": name}
        if lang := comicbox_alternative_name.get(LANGUAGE_KEY):
            metron_alternative_name[LANG_ATTR] = lang
        metron_id_attribute_from_cb(
            metron_alternative_name, comicbox_alternative_name, primary_id_source
        )
        metron_alternative_names.append(metron_alternative_name)
    return metron_alternative_names


METRON_ALTERNATIVE_NAMES_TRANSFORM_TO_CB = MetaSpec(
    key_map={
        ALTERNATIVE_NAMES_KEYPATH: (ALTERNATIVE_NAMES_TAGPATH, SCOPE_PRIMARY_SOURCE)
    },
    spec=_alternative_names_to_cb,
)
METRON_ALTERNATIVE_NAMES_TRANSFORM_FROM_CB = MetaSpec(
    key_map={
        ALTERNATIVE_NAMES_TAGPATH: (
            ALTERNATIVE_NAMES_KEYPATH,
            PRIMARY_ID_SOURCE_KEYPATH,
        )
    },
    spec=_alternative_names_from_cb,
)
