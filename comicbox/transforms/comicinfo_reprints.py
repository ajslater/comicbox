"""ComicInfo Reprints (Alternates) Schema Mixin."""

from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
)
from comicbox.transforms.transform_map import (
    KeyTransforms,
    create_transform_map,
    transform_map,
)


class ComicInfoReprintsTransformMixin:
    """ComicInfo Reprints (Alternates) Transform Mixin."""

    REPRINTS_TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "AlternateSeries": f"{SERIES_KEY}.name",
                "AlternateNumber": ISSUE_KEY,
                "AlternateCount": f"volume.{VOLUME_ISSUE_COUNT_KEY}",
            }
        )
    )

    def parse_reprints(self, data):
        """Parse reprints from alternate tags."""
        # TODO Doing this with the main transform requires passing data to the transform to get reprints and merge
        if alternative_reprint := transform_map(self.REPRINTS_TRANSFORM_MAP, data):
            old_reprints = data.get(REPRINTS_KEY, ())
            reprints = [*old_reprints, alternative_reprint]
            data[REPRINTS_KEY] = reprints
        return data

    def unparse_reprints(self, data):
        """Unparse a reprint to alternate tags."""
        reprints = data.pop(REPRINTS_KEY, None)
        if not reprints:
            return data
        first_reprint = reprints[0]
        update_dict = transform_map(self.REPRINTS_TRANSFORM_MAP.inverse, first_reprint)
        data.update(update_dict)
        return data
