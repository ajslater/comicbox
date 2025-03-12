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


def reprint_to_filename(reprint):
    """Comicbox reprint to filename."""
    # TODO use generic remapper
    filename_dict = {}
    if series := reprint.get(SERIES_KEY, {}).get(NAME_KEY):
        filename_dict[SERIES_TAG] = series
    if volume := reprint.get(VOLUME_KEY):
        volume_number = volume.get(VOLUME_NUMBER_KEY)
        if volume_number is not None:
            filename_dict[VOLUME_TAG] = volume_number
        if issue_count := volume.get(VOLUME_ISSUE_COUNT_KEY):
            filename_dict[ISSUE_COUNT_TAG] = issue_count
    if issue := reprint.get(ISSUE_KEY):
        filename_dict[ISSUE_TAG] = issue
    return dict2comicfn(filename_dict, ext=False)
