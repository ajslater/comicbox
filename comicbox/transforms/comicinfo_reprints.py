"""ComicInfo Reprints (Alternates) Schema Mixin."""

from copy import deepcopy

from bidict import bidict

from comicbox.schemas.comicbox_mixin import (
    ISSUE_COUNT_KEY,
    ISSUE_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
)
from comicbox.transforms.reprints import sort_reprints

ALTERNATE_SERIES_KEY = "alternate_series"
ALTERNATE_ISSUE_KEY = "alternate_issue"
ALTERNATE_ISSUE_COUNT_KEY = "alternate_issue_count"

ALTERNATE_COUNT_TAG = "AlternateCount"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_SERIES_TAG = "AlternateSeries"

REPRINT_KEY_MAP = bidict(
    {
        ALTERNATE_SERIES_TAG: SERIES_KEY + ".name",
        ALTERNATE_NUMBER_TAG: ISSUE_KEY,
        ALTERNATE_COUNT_TAG: "volume." + ISSUE_COUNT_KEY,
    }
)


def move_key_to_dict(key_map, source_dict):
    """Move a value with one key to another dict and mapped key."""
    target_dict = {}
    for tag, key in key_map.items():
        # Tags
        tags = tag.split(".")
        tag_value = deepcopy(source_dict)
        for subtag in tags:
            tag_value = tag_value.get(subtag)
            if tag_value is None:
                break

        if tag_value is None:
            continue

        # Keys
        keys = key.split(".")
        target_value = tag_value
        for subkey in reversed(keys[1:]):
            target_value = {subkey: target_value}
        target_dict[keys[0]] = target_value
    return dict(sorted(target_dict.items()))


class ComicInfoReprintsTransformMixin:
    """ComicInfo Reprints (Alternates) Transform Mixin."""

    def parse_reprints(self, data):
        """Parse reprints from alternate tags."""
        if reprint := move_key_to_dict(REPRINT_KEY_MAP, data):
            old_reprints = data.get(REPRINTS_KEY, [])
            reprints = [*old_reprints, reprint]
            reprints = sort_reprints(reprints)
            data[REPRINTS_KEY] = reprints
        return data

    def unparse_reprints(self, data):
        """Unparse a reprint to alternate tags."""
        reprints = data.pop(REPRINTS_KEY, None)
        if not reprints:
            return data
        reprint = reprints[0]
        update_dict = move_key_to_dict(REPRINT_KEY_MAP.inverse, reprint)

        if update_dict:
            for key, value in update_dict.items():
                if data.get(key) in (None, ""):
                    data[key] = value
        return data
