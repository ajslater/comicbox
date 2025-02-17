"""CoMet transforms."""

from types import MappingProxyType

from bidict import bidict
from stringcase import camelcase

from comicbox.schemas.comet import (
    COLORIST_TAG,
    COVER_DESIGNER_TAG,
    CREATOR_TAG,
    EDITOR_TAG,
    IDENTIFIER_TAG,
    INKER_TAG,
    IS_VERSION_OF_TAG,
    LETTERER_TAG,
    PENCILLER_TAG,
    WRITER_TAG,
    CoMetSchema,
)
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    COLORIST_KEY,
    COVER_ARTIST_KEY,
    CREATOR_KEY,
    EDITOR_KEY,
    GENRES_KEY,
    INKER_KEY,
    LETTERER_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PENCILLER_KEY,
    SUMMARY_KEY,
    WRITER_KEY,
)
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.price_mixin import PriceMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.xml_credits import XmlCreditsTransformMixin
from comicbox.transforms.xml_transforms import XmlTransform


class CoMetTransform(
    XmlTransform,
    XmlCreditsTransformMixin,
    CoMetReprintsTransformMixin,
    NestedPublishingTagsMixin,
    IdentifiersTransformMixin,
    TitleStoriesMixin,
    PriceMixin,
):
    """CoMet transforms."""

    TRANSFORM_MAP = bidict(
        {
            "coverImage": "cover_image",
            # "date": "date", handled by code
            "description": SUMMARY_KEY,
            "format": ORIGINAL_FORMAT_KEY,
            # IDENTIFIER_TAG: "identifiers", handled by code
            # "language": LANGUAGE_KEY, handled by code
            "lastMark": "last_mark",
            "pages": PAGE_COUNT_KEY,
            # "publisher": "publisher", handled by code
            # "price": PRICES_KEY coded
            "rating": "age_rating",
            "readingDirection": "reading_direction",
            # "rights": "rights", unused
            # "series": SERIES_KEY,  handled by code
            # "title": "title", handled by code
            # "volume": VOLUME_KEY, handled by code
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            "character": CHARACTERS_KEY,
            "genre": GENRES_KEY,
        }
    )
    CONTRIBUTOR_SCHEMA_MAP = bidict(
        {
            COLORIST_KEY: COLORIST_TAG,
            COVER_ARTIST_KEY: COVER_DESIGNER_TAG,
            CREATOR_KEY: CREATOR_TAG,  # Unused
            EDITOR_KEY: EDITOR_TAG,
            INKER_KEY: INKER_TAG,
            LETTERER_KEY: LETTERER_TAG,
            PENCILLER_KEY: PENCILLER_TAG,
            WRITER_KEY: WRITER_TAG,
        }
    )
    CONTRIBUTOR_COMICBOX_MAP = CONTRIBUTOR_SCHEMA_MAP.inverse

    SCHEMA_CLASS = CoMetSchema
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None
    PUBLISHER_TAG = "publisher"
    SERIES_TAG = "series"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = ""
    TITLE_TAG = "title"
    PRICE_TAG = "price"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.aggregate_contributors,
        CoMetReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
        PriceMixin.parse_price,
    )
    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.disaggregate_contributors,
        CoMetReprintsTransformMixin.unparse_reprints,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        PriceMixin.unparse_price,
    )

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return camelcase(data)
