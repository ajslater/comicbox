"""Comictagger Aliases to reprints."""

from comicfn2dict.parse import comicfn2dict
from glom import SKIP, Coalesce, Flatten, T

from comicbox.empty import is_empty
from comicbox.schemas.comicbox import (
    NAME_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
)
from comicbox.schemas.comictagger import (
    IS_VERSION_OF_TAG,
    SERIES_ALIASES_TAG,
    TITLE_ALIASES_TAG,
)
from comicbox.transforms.spec import MetaSpec
from comicbox.transforms.xml_reprints import FILENAME_TO_REPRINT_SPECS

SERIES_NAME_KEYPATH = f"{SERIES_KEY}.{NAME_KEY}"


CT_REPRINTS_TRANSFORM_TO_CB = MetaSpec(
    key_map={
        REPRINTS_KEY: (IS_VERSION_OF_TAG, SERIES_ALIASES_TAG, TITLE_ALIASES_TAG),
    },
    spec=(
        {
            IS_VERSION_OF_TAG: [
                Coalesce(
                    (T[IS_VERSION_OF_TAG], comicfn2dict, FILENAME_TO_REPRINT_SPECS),
                    skip=is_empty,
                    default=SKIP,
                )
            ],
            SERIES_ALIASES_TAG: [
                Coalesce(
                    (T[SERIES_ALIASES_TAG], SERIES_NAME_KEYPATH),
                    skip=is_empty,
                    default=SKIP,
                )
            ],
        },
        Flatten(T.values()),
    ),
)


CT_SERIES_ALIASES_TRANSFORM_FROM_CB = MetaSpec(
    key_map={SERIES_ALIASES_TAG: REPRINTS_KEY},
    spec=([(Coalesce(SERIES_NAME_KEYPATH, default=SKIP))],),
)
