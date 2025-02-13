"""Transforms to and from ComicRack's ComicInfo.xml schema."""

from bidict import bidict

from comicbox.identifiers import GTIN_NID
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    COLORIST_KEY,
    COVER_ARTIST_KEY,
    CREATOR_KEY,
    EDITOR_KEY,
    GENRES_KEY,
    INKER_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LETTERER_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PENCILLER_KEY,
    SCAN_INFO_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    WRITER_KEY,
)
from comicbox.schemas.comicinfo import (
    COLORIST_TAG,
    COVER_ARTIST_TAG,
    CREATOR_TAG,
    EDITOR_TAG,
    GTIN_TAG,
    INKER_TAG,
    LETTTER_TAG,
    PENCILLER_TAG,
    WRITER_TAG,
    ComicInfoSchema,
)
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.comicinfo_reprints import (
    ComicInfoReprintsTransformMixin,
)
from comicbox.transforms.comicinfo_storyarcs import (
    ComicInfoStoryArcsTransformMixin,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.xml_credits import XmlCreditsTransformMixin
from comicbox.transforms.xml_transforms import XmlTransform


class ComicInfoTransform(
    ComicInfoPagesTransformMixin,
    ComicInfoReprintsTransformMixin,
    ComicInfoStoryArcsTransformMixin,
    IdentifiersTransformMixin,
    NestedPublishingTagsMixin,
    XmlCreditsTransformMixin,
    TitleStoriesMixin,
):
    """ComicInfo.xml Schema."""

    TRANSFORM_MAP = bidict(
        {
            "AgeRating": "age_rating",
            # REPRINTS
            # "AlternateCount": ALTERNATE_ISSUE_COUNT_KEY, coded
            # "AlternateNumber": ALTERNATE_ISSUE_KEY, coded
            # "AlternateSeries": ALTERNATE_SERIES_KEY, coded
            #
            "BlackAndWhite": "monochrome",
            "Characters": CHARACTERS_KEY,
            "CommunityRating": "community_rating",
            "Country": "country",
            # "Count": ISSUE_COUNT_KEY, coded
            "Day": "day",
            "Genre": GENRES_KEY,
            # "GTIN": IDENTIFIERS_KEY, coded
            "Format": ORIGINAL_FORMAT_KEY,
            # "Imprint": IMPRINT_KEY, coded
            "LanguageISO": LANGUAGE_KEY,
            "Locations": "locations",
            "MainCharacterOrTeam": "protagonist",
            "Manga": "manga",
            "Month": "month",
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
            # "Pages": PAGES_KEY, coded
            # "Publisher": PUBLISHER_KEY coded
            "Review": "review",
            "ScanInformation": SCAN_INFO_KEY,
            # "Series": SERIES_KEY, coded
            "SeriesGroup": "series_groups",
            # STORY_ARCS
            # "StoryArc": STORY_ARC_KEY, coded
            # "StoryArcNumber": STORY_ARC_NUMBER_KEY, coded
            ##
            "Tags": TAGS_KEY,
            "Teams": TEAMS_KEY,
            # "Title": "title", coded
            "Summary": SUMMARY_KEY,
            # "Volume": VOLUME_KEY, coded
            # "Web": WEB_KEY, coded
            "Year": "year",
        }
    )

    CONTRIBUTOR_SCHEMA_MAP = bidict(
        {
            COLORIST_KEY: COLORIST_TAG,
            COVER_ARTIST_KEY: COVER_ARTIST_TAG,
            CREATOR_KEY: CREATOR_TAG,
            EDITOR_KEY: EDITOR_TAG,
            INKER_KEY: INKER_TAG,
            LETTERER_KEY: LETTTER_TAG,
            PENCILLER_KEY: PENCILLER_TAG,
            WRITER_KEY: WRITER_TAG,
        }
    )
    CONTRIBUTOR_COMICBOX_MAP = CONTRIBUTOR_SCHEMA_MAP.inverse
    SCHEMA_CLASS = ComicInfoSchema
    IDENTIFIERS_TAG = GTIN_TAG
    NAKED_NID = GTIN_NID
    PUBLISHER_TAG = "Publisher"
    IMPRINT_TAG = "Imprint"
    SERIES_TAG = "Series"
    VOLUME_TAG = "Volume"
    ISSUE_COUNT_TAG = "Count"
    URLS_TAG = "Web"
    TITLE_TAG = "Title"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.aggregate_contributors,
        ComicInfoPagesTransformMixin.parse_pages,
        ComicInfoStoryArcsTransformMixin.aggregate_story_arcs,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_imprint,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        ComicInfoReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        TitleStoriesMixin.parse_stories,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.disaggregate_contributors,
        ComicInfoPagesTransformMixin.unparse_pages,
        ComicInfoReprintsTransformMixin.unparse_reprints,
        ComicInfoStoryArcsTransformMixin.disaggregate_story_arcs,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_imprint,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
    )
