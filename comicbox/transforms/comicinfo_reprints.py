"""ComicInfo Reprints (Alternates) Schema Mixin."""

from bidict import frozenbidict

from comicbox.dict_funcs import move_key_to_dict
from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
)

ALTERNATE_SERIES_KEY = "alternate_series"
ALTERNATE_ISSUE_KEY = "alternate_issue"
ALTERNATE_ISSUE_COUNT_KEY = "alternate_issue_count"

ALTERNATE_COUNT_TAG = "AlternateCount"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_SERIES_TAG = "AlternateSeries"

REPRINT_KEY_MAP = frozenbidict(
    {
        ALTERNATE_SERIES_TAG: SERIES_KEY + ".name",
        ALTERNATE_NUMBER_TAG: ISSUE_KEY,
        ALTERNATE_COUNT_TAG: "volume." + VOLUME_ISSUE_COUNT_KEY,
    }
)


class ComicInfoReprintsTransformMixin:
    """ComicInfo Reprints (Alternates) Transform Mixin."""

    def parse_reprints(self, data):
        """Parse reprints from alternate tags."""
        if reprint := move_key_to_dict(REPRINT_KEY_MAP, data):
            old_reprints = data.get(REPRINTS_KEY, [])
            reprints = [*old_reprints, reprint]
            data[REPRINTS_KEY] = reprints
        return data

    def unparse_reprints(self, data):
        """Unparse a reprint to alternate tags."""
        reprints = data.pop(REPRINTS_KEY, None)
        if not reprints:
            return data
        reprint = reprints[0]
        update_dict = move_key_to_dict(REPRINT_KEY_MAP.inverse, reprint)
        data.update(update_dict)
        return data
