"""MetronInfo.xml Transformer."""

from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    COLLECTION_TITLE_KEY,
    DATE_KEY,
    ISSUE_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    STORE_DATE_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.metroninfo import (
    MetronInfoSchema,
)
from comicbox.transforms.metroninfo.credits import METRON_CREDITS_TRANSFORM
from comicbox.transforms.metroninfo.identifiers import (
    METRON_GTIN_TRANSFORM,
    METRON_IDENTIFIERS_TRANSFORM,
    METRON_PRIMARY_SOURCE_KEY_TRANSFORM,
    METRON_URLS_TRANSFORM,
)
from comicbox.transforms.metroninfo.publishing_tags import (
    METRON_IMPRINT_TRANSFORM,
    METRON_MANGA_VOLUME_TRANSFORM,
    METRON_PUBLISHER_TRANSFORM,
    METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM,
    METRON_SERIES_IDENTIFIERS_TRANSFORM,
    SERIES_KEY_MAP,
)
from comicbox.transforms.metroninfo.reprints import METRON_REPRINTS_TRANSFORM
from comicbox.transforms.metroninfo.resources import (
    METRON_ARCS_TRANSFORM,
    METRON_PRICES_TRANSFORM,
    METRON_RESOURCES_TRANSFORMS,
    METRON_UNIVERSES_TRANSFORM,
)
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.transforms.xml_transforms import XmlTransform


class MetronInfoTransform(XmlTransform):
    """MetronInfo.xml Transformer."""

    SCHEMA_CLASS = MetronInfoSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "AgeRating": AGE_RATING_KEY,
                "CollectionTitle": COLLECTION_TITLE_KEY,
                "CoverDate": DATE_KEY,
                "StoreDate": STORE_DATE_KEY,
                "Notes": NOTES_KEY,
                "Number": ISSUE_KEY,
                "PageCount": PAGE_COUNT_KEY,
                "Summary": SUMMARY_KEY,
                "LastModified": UPDATED_AT_KEY,
                **SERIES_KEY_MAP,
            }
        ),
        METRON_ARCS_TRANSFORM,
        METRON_CREDITS_TRANSFORM,
        METRON_PUBLISHER_TRANSFORM,
        METRON_IMPRINT_TRANSFORM,
        METRON_SERIES_IDENTIFIERS_TRANSFORM,
        METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM,
        METRON_MANGA_VOLUME_TRANSFORM,
        METRON_PRICES_TRANSFORM,
        METRON_GTIN_TRANSFORM,
        METRON_IDENTIFIERS_TRANSFORM,
        METRON_PRIMARY_SOURCE_KEY_TRANSFORM,
        METRON_REPRINTS_TRANSFORM,
        METRON_URLS_TRANSFORM,
        *METRON_RESOURCES_TRANSFORMS,
        METRON_UNIVERSES_TRANSFORM,
    )
