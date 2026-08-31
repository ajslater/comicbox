"""CoMet Reprints Transforms."""

from typing import Any

from comicfn2dict.parse import comicfn2dict
from comicfn2dict.unparse import dict2comicfn
from glom import glom

from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.base.transforms.xml_reprints import (
    FILENAME_TO_REPRINT_SPECS,
    REPRINT_TO_FILENAME_SPECS,
)
from comicbox.formats.comicbox.schema import NAME_KEY, REPRINTS_KEY


def comet_reprints_transform_to_cb(is_version_of_tag: str) -> MetaSpec:
    """
    Transform comet is_version_of to reprints.

    CoMet allows one isVersionOf, so this reads a single name.
    """

    def to_cb(comet_is_version_of: Any) -> list:
        if not comet_is_version_of:
            return []
        name = str(comet_is_version_of)
        # isVersionOf is the reprint's name, so it is stored as one. The
        # parsed fields are enrichment, as they are for MetronInfo.
        filename_dict = comicfn2dict(name)
        reprint = glom(filename_dict, dict(FILENAME_TO_REPRINT_SPECS))
        reprint[NAME_KEY] = name
        return [reprint]

    return MetaSpec(key_map={REPRINTS_KEY: is_version_of_tag}, spec=to_cb)


def comet_reprints_transform_from_cb(is_version_of_tag: str) -> MetaSpec:
    """
    Transform reprints to comet is_version_of.

    Only the first reprint fits CoMet's single tag.
    """

    def from_cb(comicbox_reprints: Any) -> str:
        if not comicbox_reprints:
            return ""
        reprint = comicbox_reprints[0]
        if name := reprint.get(NAME_KEY):
            return str(name)
        filename_dict = glom(reprint, dict(REPRINT_TO_FILENAME_SPECS))
        return dict2comicfn(filename_dict, ext=False) or ""

    return MetaSpec(key_map={is_version_of_tag: REPRINTS_KEY}, spec=from_cb)
