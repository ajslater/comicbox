"""Reprint sorting."""

from comicfn2dict.unparse import dict2comicfn

from comicbox.schemas.comicbox_mixin import (
    IMPRINT_KEY,
    ISSUE_COUNT_KEY,
    ISSUE_KEY,
    PUBLISHER_KEY,
    SERIES_KEY,
    SERIES_NAME_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.filename import ISSUE_COUNT_TAG, ISSUE_TAG, SERIES_TAG, VOLUME_TAG


def _reprint_key(reprint):
    series = reprint.get(SERIES_KEY, {})
    volume = reprint.get(VOLUME_KEY, {})
    return ":".join(
        (
            str(reprint.get(PUBLISHER_KEY)),
            str(reprint.get(IMPRINT_KEY)),
            str(series.get(SERIES_NAME_KEY)),
            str(series.get(VOLUME_COUNT_KEY)),
            str(volume.get(VOLUME_NUMBER_KEY)),
            str(volume.get(ISSUE_COUNT_KEY)),
            str(reprint.get(ISSUE_KEY)),
        )
    )


def sort_reprints(reprints):
    """Sort and uniquify a list of reprints."""
    reprint_dict = {}
    for reprint in reprints:
        reprint_dict[_reprint_key(reprint)] = reprint
    reprint_dict = dict(sorted(reprint_dict.items()))
    return list(reprint_dict.values())


def reprint_to_filename(reprint):
    """Comicbox reprint to filename."""
    filename_dict = {}
    if series := reprint.get(SERIES_KEY, {}).get(SERIES_NAME_KEY):
        filename_dict[SERIES_TAG] = series
    if volume := reprint.get(VOLUME_KEY):
        volume_number = volume.get(VOLUME_NUMBER_KEY)
        if volume_number is not None:
            filename_dict[VOLUME_TAG] = volume_number
        if issue_count := volume.get(ISSUE_COUNT_KEY):
            filename_dict[ISSUE_COUNT_TAG] = issue_count
    if issue := reprint.get(ISSUE_KEY):
        filename_dict[ISSUE_TAG] = issue
    return dict2comicfn(filename_dict, ext=False)
