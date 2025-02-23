"""Transforms to and from ComicRack's ComicInfo.xml schema."""

from types import MappingProxyType

from bidict import bidict

from comicbox.identifiers import GTIN_NID
from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    COUNTRY_KEY,
    DAY_KEY,
    GENRES_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    MONTH_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    SCAN_INFO_KEY,
    SERIES_GROUPS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    YEAR_KEY,
)
from comicbox.schemas.comicinfo import (
    GTIN_TAG,
    ComicInfoRoleTagEnum,
    ComicInfoSchema,
)
from comicbox.schemas.metroninfo import MetronRoleEnum
from comicbox.transforms.comicinfo_age_rating import ComicInfoAgeRatingTransform
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.comicinfo_reprints import (
    ComicInfoReprintsTransformMixin,
)
from comicbox.transforms.comicinfo_storyarcs import (
    ComicInfoStoryArcsTransformMixin,
)
from comicbox.transforms.credit_role_tag import create_role_map
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
    ComicInfoAgeRatingTransform,
):
    """ComicInfo.xml Schema."""

    TRANSFORM_MAP = bidict(
        {
            # "AgeRating": AGE_RATING_KEY, coded
            # REPRINTS
            # "AlternateCount": ALTERNATE_ISSUE_COUNT_KEY, coded
            # "AlternateNumber": ALTERNATE_ISSUE_KEY, coded
            # "AlternateSeries": ALTERNATE_SERIES_KEY, coded
            #
            "BlackAndWhite": "monochrome",
            "CommunityRating": "community_rating",
            "Country": COUNTRY_KEY,
            # "Count": ISSUE_COUNT_KEY, coded
            "Day": DAY_KEY,
            # "GTIN": IDENTIFIERS_KEY, coded
            "Format": ORIGINAL_FORMAT_KEY,
            # "Imprint": IMPRINT_KEY, coded
            "LanguageISO": LANGUAGE_KEY,
            "MainCharacterOrTeam": "protagonist",
            "Manga": "manga",
            "Month": MONTH_KEY,
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
            # "Pages": PAGES_KEY, coded
            # "Publisher": PUBLISHER_KEY coded
            "Review": "review",
            "ScanInformation": SCAN_INFO_KEY,
            # "Series": SERIES_KEY, coded
            # STORY_ARCS
            # "StoryArc": STORY_ARC_KEY, coded
            # "StoryArcNumber": STORY_ARC_NUMBER_KEY, coded
            ##
            # "Title": "title", coded
            "Summary": SUMMARY_KEY,
            # "Volume": VOLUME_KEY, coded
            # "Web": WEB_KEY, coded
            "Year": YEAR_KEY,
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            "Characters": CHARACTERS_KEY,
            "Genre": GENRES_KEY,
            "Locations": LOCATIONS_KEY,
            "SeriesGroup": SERIES_GROUPS_KEY,
            "Tags": TAGS_KEY,
            "Teams": TEAMS_KEY,
        }
    )
    ROLE_TAGS_ENUM = ComicInfoRoleTagEnum
    PRE_ROLE_MAP = MappingProxyType(
        {
            **{enum: enum for enum in ComicInfoRoleTagEnum},
            CoMetRoleTagEnum.COLORIST: ComicInfoRoleTagEnum.COLORIST,
            CoMetRoleTagEnum.COVER_DESIGNER: ComicInfoRoleTagEnum.COVER_ARTIST,
            # CoMetRoleTagEnum.creator:ComicInfoRoleTagEnum.,
            CoMetRoleTagEnum.EDITOR: ComicInfoRoleTagEnum.EDITOR,
            CoMetRoleTagEnum.INKER: ComicInfoRoleTagEnum.INKER,
            CoMetRoleTagEnum.PENCILLER: ComicInfoRoleTagEnum.PENCILLER,
            ComicBookInfoRoleEnum.ARTIST: (
                ComicInfoRoleTagEnum.WRITER,
                ComicInfoRoleTagEnum.PENCILLER,
            ),
            # ComicBookInfoRoleEnum.OTHER: ComicInfoRoleTagEnum.,
            MetronRoleEnum.WRITER: ComicInfoRoleTagEnum.WRITER,
            MetronRoleEnum.SCRIPT: ComicInfoRoleTagEnum.WRITER,
            MetronRoleEnum.STORY: ComicInfoRoleTagEnum.WRITER,
            MetronRoleEnum.PLOT: ComicInfoRoleTagEnum.WRITER,
            MetronRoleEnum.INTERVIEWER: ComicInfoRoleTagEnum.WRITER,
            MetronRoleEnum.ARTIST: (
                ComicInfoRoleTagEnum.WRITER,
                ComicInfoRoleTagEnum.PENCILLER,
            ),
            MetronRoleEnum.PENCILLER: ComicInfoRoleTagEnum.PENCILLER,
            MetronRoleEnum.BREAKDOWNS: ComicInfoRoleTagEnum.PENCILLER,
            MetronRoleEnum.ILLUSTRATOR: ComicInfoRoleTagEnum.PENCILLER,
            MetronRoleEnum.LAYOUTS: ComicInfoRoleTagEnum.PENCILLER,
            MetronRoleEnum.INKER: ComicInfoRoleTagEnum.INKER,
            MetronRoleEnum.EMBELLISHER: ComicInfoRoleTagEnum.INKER,
            MetronRoleEnum.FINISHES: ComicInfoRoleTagEnum.INKER,
            MetronRoleEnum.INK_ASSISTS: ComicInfoRoleTagEnum.INKER,
            MetronRoleEnum.COLORIST: ComicInfoRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_SEPARATIONS: ComicInfoRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_ASSISTS: ComicInfoRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_FLATS: ComicInfoRoleTagEnum.COLORIST,
            # MetronRoleEnum.DIGITAL_ART_TECHNICIAN: ComicInfoRoleTagEnum.,
            MetronRoleEnum.GRAY_TONE: ComicInfoRoleTagEnum.COLORIST,
            MetronRoleEnum.LETTERER: ComicInfoRoleTagEnum.LETTERER,
            MetronRoleEnum.COVER: ComicInfoRoleTagEnum.COVER_ARTIST,
            MetronRoleEnum.EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.CONSULTING_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.ASSISTANT_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.ASSOCIATE_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.GROUP_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.SENIOR_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.MANAGING_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.COLLECTION_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.PRODUCTION: ComicInfoRoleTagEnum.EDITOR,
            # MetronRoleEnum.DESIGNER: ComicInfoRoleTagEnum.,
            # MetronRoleEnum.LOGO_DESIGN: ComicInfoRoleTagEnum.,
            MetronRoleEnum.TRANSLATOR: ComicInfoRoleTagEnum.TRANSLATOR,
            MetronRoleEnum.SUPERVISING_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.EXECUTIVE_EDITOR: ComicInfoRoleTagEnum.EDITOR,
            MetronRoleEnum.EDITOR_IN_CHIEF: ComicInfoRoleTagEnum.EDITOR,
            # MetronRoleEnum.PRESIDENT: ComicInfoRoleTagEnum.,
            # MetronRoleEnum.CHIEF_CREATIVE_OFFICER: ComicInfoRoleTagEnum.,
            # MetronRoleEnum.EXECUTIVE_PRODUCER: ComicInfoRoleTagEnum.,
            # MetronRoleEnum.OTHER: ComicInfoRoleTagEnum.,
        }
    )
    ROLE_MAP = create_role_map(PRE_ROLE_MAP)
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
    AGE_RATING_TAG = "AgeRating"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.parse_credits,
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
        ComicInfoAgeRatingTransform.parse_age_rating,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.unparse_credits,
        ComicInfoPagesTransformMixin.unparse_pages,
        ComicInfoReprintsTransformMixin.unparse_reprints,
        ComicInfoStoryArcsTransformMixin.disaggregate_story_arcs,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_imprint,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        ComicInfoAgeRatingTransform.unparse_age_rating,
    )
