"""CoMet transforms."""

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
    INKER_KEY,
    LETTERER_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PENCILLER_KEY,
    WRITER_KEY,
)
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.xml import XmlTransform
from comicbox.transforms.xml_credits import XmlCreditsTransformMixin


class CoMetTransform(
    XmlTransform,
    XmlCreditsTransformMixin,
    CoMetReprintsTransformMixin,
    NestedPublishingTagsMixin,
    IdentifiersTransformMixin,
):
    """CoMet transforms."""

    TRANSFORM_MAP = bidict(
        {
            "character": CHARACTERS_KEY,
            "coverImage": "cover_image",
            # "date": "date",
            "description": "summary",
            "format": ORIGINAL_FORMAT_KEY,
            "genre": "genres",
            # IDENTIFIER_TAG: "identifiers",
            # "language": LANGUAGE_KEY,
            "lastMark": "last_mark",
            "pages": PAGE_COUNT_KEY,
            # "publisher": "publisher",
            # "price": PRICE_KEY,
            "rating": "age_rating",
            "readingDirection": "reading_direction",
            # "rights": "rights",
            # "series": SERIES_KEY,
            # "title": "title",
            # "volume": VOLUME_KEY,
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
    SERIES_TAG = "series"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = ""

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.aggregate_contributors,
        CoMetReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_url_tag,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
    )
    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.disaggregate_contributors,
        CoMetReprintsTransformMixin.unparse_reprints,
        IdentifiersTransformMixin.unparse_identifiers,
        IdentifiersTransformMixin.unparse_url_tag,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
    )

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return camelcase(data)
