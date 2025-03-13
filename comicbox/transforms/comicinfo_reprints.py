"""ComicInfo Reprints (Alternates) Schema Mixin."""

from types import MappingProxyType

from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
)
from comicbox.transforms.base import create_transform_map
from comicbox.transforms.transform_map import transform_map

ALTERNATE_SERIES_KEY = "alternate_series"
ALTERNATE_ISSUE_KEY = "alternate_issue"
ALTERNATE_ISSUE_COUNT_KEY = "alternate_issue_count"

ALTERNATE_COUNT_TAG = "AlternateCount"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_SERIES_TAG = "AlternateSeries"

_REPRINT_KEY_MAP = MappingProxyType(
    {
        ALTERNATE_SERIES_TAG: f"{SERIES_KEY}.name",
        ALTERNATE_NUMBER_TAG: ISSUE_KEY,
        ALTERNATE_COUNT_TAG: f"volume.{VOLUME_ISSUE_COUNT_KEY}",
    }
)


class ComicInfoReprintsTransformMixin:
    """ComicInfo Reprints (Alternates) Transform Mixin."""

    REPRINTS_TRANSFORM_MAP = create_transform_map(_REPRINT_KEY_MAP, {})

    def parse_reprints(self, data):
        """Parse reprints from alternate tags."""
        if reprint := transform_map(self.REPRINTS_TRANSFORM_MAP, data):
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
        update_dict = transform_map(self.REPRINTS_TRANSFORM_MAP.inverse, reprint)
        data.update(update_dict)
        return data
