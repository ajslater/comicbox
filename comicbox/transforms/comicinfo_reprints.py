"""ComicInfo Reprints (Alternates) Schema Mixin."""

from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    NAME_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
)
from comicbox.transforms.transform_map import (
    DUMMY_PREFIX,
    KeyTransforms,
    MultiAssigns,
    create_transform_map,
    transform_map,
)

ALTERNATE_SERIES_TAG = "AlternateSeries"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_COUNT_TAG = "AlternateCount"
SERIES_NAME_KEY_PATH = f"{SERIES_KEY}.{NAME_KEY}"
ISSUE_KEY_PATH = ISSUE_KEY
VOLUME_COUNT_KEY_PATH = f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}"

REPRINTS_TRANSFORM_MAP = create_transform_map(
    KeyTransforms(
        key_map={
            ALTERNATE_SERIES_TAG: SERIES_NAME_KEY_PATH,
            ALTERNATE_NUMBER_TAG: ISSUE_KEY,
            ALTERNATE_COUNT_TAG: VOLUME_COUNT_KEY_PATH,
        }
    )
)


def _cix_reprints_to_cb(source_data, _alternative_series):
    if alternative_reprint := transform_map(REPRINTS_TRANSFORM_MAP, source_data):
        return [alternative_reprint]
    return None


def _cix_reprints_from_cb(_source_data, reprints):
    first_reprint = reprints[0]
    update_dict = transform_map(REPRINTS_TRANSFORM_MAP.inverse, first_reprint)
    extra_assigns = tuple(update_dict.items())
    return MultiAssigns(None, tuple(extra_assigns))


REPRINTS_KEY_TRANSFORM = KeyTransforms(
    key_map={f"{DUMMY_PREFIX}alternate_xml_tags": REPRINTS_KEY},
    to_cb=_cix_reprints_to_cb,
    from_cb=_cix_reprints_from_cb,
)
