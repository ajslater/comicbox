"""Reprint sorting."""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    ISSUE_KEY,
    NAME_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.filename import ISSUE_COUNT_TAG, ISSUE_TAG, SERIES_TAG, VOLUME_TAG
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

REPRINTS_TO_FILENAME_KEY_MAP = frozenbidict(
    {
        SERIES_TAG: f"{SERIES_KEY}.{NAME_KEY}",
        VOLUME_TAG: f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}",
        ISSUE_COUNT_TAG: f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}",
        ISSUE_TAG: f"{ISSUE_KEY}",
    }
)
FILENAME_TO_REPRINT_SPECS = create_specs_to_comicbox(
    MetaSpec(key_map=REPRINTS_TO_FILENAME_KEY_MAP.inverse, inherit_root_keypath=False)
)
REPRINT_TO_FILENAME_SPECS = create_specs_from_comicbox(
    MetaSpec(key_map=REPRINTS_TO_FILENAME_KEY_MAP, inherit_root_keypath=False)
)
