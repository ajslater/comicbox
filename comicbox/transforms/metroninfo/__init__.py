"""MetronInfo.xml Transformer."""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    AGE_RATING_KEY,
    COLLECTION_TITLE_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.metroninfo import (
    MetronInfoSchema,
)
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import (
    COVER_DATE_KEYPATH,
    ISSUE_NAME_KEYPATH,
    STORE_DATE_KEYPATH,
)
from comicbox.transforms.metroninfo.credits import (
    METRON_CREDITS_TRANSFORM_TO_CB,
    metron_credits_from_cb,
)
from comicbox.transforms.metroninfo.identifiers import (
    METRON_GTIN_TRANSFORM_FROM_CB,
    METRON_IDENTIFIERS_TRANSFORM_FROM_CB,
    METRON_IDENTIFIERS_TRANSFORM_TO_CB,
    METRON_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB,
    METRON_URLS_TRANSFORM_FROM_CB,
)
from comicbox.transforms.metroninfo.publishing_tags import (
    METRON_IMPRINT_TRANSFORM_TO_CB,
    METRON_MANGA_VOLUME_TRANSFORM_FROM_CB,
    METRON_PUBLISHER_TRANSFORM_FROM_CB,
    METRON_PUBLISHER_TRANSFORM_TO_CB,
    METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM_FROM_CB,
    METRON_SERIES_IDENTIFIER_TRANSFORM_FROM_CB,
    METRON_SERIES_IDENTIFIER_TRANSFORM_TO_CB,
    METRON_SERIES_TRANSFORM_FROM_CB,
    METRON_SERIES_TRANSFORM_TO_CB,
    METRON_VOLUME_TRANSFORM_TO_CB,
)
from comicbox.transforms.metroninfo.reprints import (
    METRON_REPRINTS_TRANSFORM_FROM_CB,
    METRON_REPRINTS_TRANSFORM_TO_CB,
)
from comicbox.transforms.metroninfo.resources import (
    METRON_ARCS_TRANSFORM_FROM_CB,
    METRON_ARCS_TRANSFORM_TO_CB,
    METRON_PRICES_TRANSFORM_FROM_CB,
    METRON_PRICES_TRANSFORM_TO_CB,
    METRON_RESOURCES_TRANSFORMS_FROM_CB,
    METRON_RESOURCES_TRANSFORMS_TO_CB,
    METRON_UNIVERSES_TRANSFORM_FROM_CB,
    METRON_UNIVERSES_TRANSFORM_TO_CB,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

SIMPLE_KEY_MAP = frozenbidict(
    {
        "AgeRating": AGE_RATING_KEY,
        "CollectionTitle": COLLECTION_TITLE_KEY,
        "CoverDate": COVER_DATE_KEYPATH,
        "StoreDate": STORE_DATE_KEYPATH,
        "Notes": NOTES_KEY,
        "Number": ISSUE_NAME_KEYPATH,
        "PageCount": PAGE_COUNT_KEY,
        "Summary": SUMMARY_KEY,
        "LastModified": UPDATED_AT_KEY,
    }
)


class MetronInfoTransform(BaseTransform):
    """MetronInfo.xml Transformer."""

    SCHEMA_CLASS = MetronInfoSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP.inverse),
        METRON_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB,  # must come before most other resources
        METRON_ARCS_TRANSFORM_TO_CB,
        METRON_CREDITS_TRANSFORM_TO_CB,
        METRON_PUBLISHER_TRANSFORM_TO_CB,
        METRON_IMPRINT_TRANSFORM_TO_CB,
        METRON_SERIES_TRANSFORM_TO_CB,
        METRON_SERIES_IDENTIFIER_TRANSFORM_TO_CB,  # best if after series.
        METRON_VOLUME_TRANSFORM_TO_CB,
        METRON_PRICES_TRANSFORM_TO_CB,
        METRON_IDENTIFIERS_TRANSFORM_TO_CB,
        METRON_REPRINTS_TRANSFORM_TO_CB,
        *METRON_RESOURCES_TRANSFORMS_TO_CB,
        METRON_UNIVERSES_TRANSFORM_TO_CB,
        format_root_keypath=MetronInfoSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        METRON_ARCS_TRANSFORM_FROM_CB,
        metron_credits_from_cb(),
        METRON_PUBLISHER_TRANSFORM_FROM_CB,
        METRON_SERIES_TRANSFORM_FROM_CB,
        METRON_SERIES_IDENTIFIER_TRANSFORM_FROM_CB,
        METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM_FROM_CB,
        METRON_MANGA_VOLUME_TRANSFORM_FROM_CB,
        METRON_PRICES_TRANSFORM_FROM_CB,
        METRON_GTIN_TRANSFORM_FROM_CB,
        METRON_IDENTIFIERS_TRANSFORM_FROM_CB,
        METRON_REPRINTS_TRANSFORM_FROM_CB,
        METRON_URLS_TRANSFORM_FROM_CB,
        *METRON_RESOURCES_TRANSFORMS_FROM_CB,
        METRON_UNIVERSES_TRANSFORM_FROM_CB,
        format_root_keypath=MetronInfoSchema.ROOT_KEYPATH,
    )
