"""Reprint sorting."""

from comicfn2dict.parse import comicfn2dict
from comicfn2dict.unparse import dict2comicfn

from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    NAME_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.filename import ISSUE_COUNT_TAG, ISSUE_TAG, SERIES_TAG, VOLUME_TAG
from comicbox.transforms.transform_map import (
    KeyTransforms,
    create_transform_map,
    transform_map,
)

REPRINTS_TO_FILENAME_TRANSFORM_MAP = create_transform_map(
    KeyTransforms(
        key_map={
            SERIES_TAG: f"{SERIES_KEY}.{NAME_KEY}",
            VOLUME_TAG: f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}",
            ISSUE_COUNT_TAG: f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}",
            ISSUE_TAG: f"{ISSUE_KEY}",
        }
    ),
    comicbox_root_key="",
)


def filename_to_reprint(filename):
    """Filename to comicbox reprint."""
    filename_dict = comicfn2dict(filename)
    return transform_map(REPRINTS_TO_FILENAME_TRANSFORM_MAP, filename_dict)


def reprint_to_filename(reprint):
    """Comicbox reprint to filename."""
    filename_dict = transform_map(REPRINTS_TO_FILENAME_TRANSFORM_MAP.inverse, reprint)
    return dict2comicfn(filename_dict, ext=False)
