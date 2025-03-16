"""Reprint sorting."""

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
            f"{SERIES_KEY}.{NAME_KEY}": SERIES_TAG,
            f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}": VOLUME_TAG,
            f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}": ISSUE_COUNT_TAG,
            f"{ISSUE_KEY}": ISSUE_TAG,
        }
    )
)


def reprint_to_filename(reprint):
    """Comicbox reprint to filename."""
    filename_dict = transform_map(REPRINTS_TO_FILENAME_TRANSFORM_MAP, reprint)
    return dict2comicfn(filename_dict, ext=False)
