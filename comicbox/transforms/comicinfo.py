"""Transforms to and from ComicRack's ComicInfo.xml schema."""

from enum import Enum
from types import MappingProxyType

from comicbox.identifiers import GTIN_NID
from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COMMUNITY_RATING_KEY,
    COUNTRY_KEY,
    DAY_KEY,
    GENRES_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    MONOCHROME_KEY,
    MONTH_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PROTAGONIST_KEY,
    REVIEW_KEY,
    SCAN_INFO_KEY,
    SERIES_GROUPS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    YEAR_KEY,
)
from comicbox.schemas.comicinfo import (
    GTIN_TAG,
    ComicInfoSchema,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import create_transform_map
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.comicinfo_reprints import (
    ComicInfoReprintsTransformMixin,
)
from comicbox.transforms.comicinfo_storyarcs import (
    ComicInfoStoryArcsTransformMixin,
)
from comicbox.transforms.credit_role_tag import (
    create_role_map,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.xml_credits import XmlCreditsTransformMixin
from comicbox.transforms.xml_transforms import XmlTransform

ROLE_ALIASES: MappingProxyType[Enum, tuple[Enum | str, ...]] = MappingProxyType(
    {
        ComicInfoRoleTagEnum.COLORIST: (
            GenericRoleEnum.COLOURIST,
            *GenericRoleAliases.COLORIST.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.COLORIST,
            MetronRoleEnum.COLORIST,
            MetronRoleEnum.COLOR_SEPARATIONS,
            MetronRoleEnum.COLOR_ASSISTS,
            MetronRoleEnum.COLOR_FLATS,
            MetronRoleEnum.GRAY_TONE,
        ),
        ComicInfoRoleTagEnum.COVER_ARTIST: (
            *GenericRoleAliases.COVER.value,
            CoMetRoleTagEnum.COVER_DESIGNER,
            MetronRoleEnum.COVER,
        ),
        ComicInfoRoleTagEnum.EDITOR: (
            *GenericRoleAliases.EDITOR.value,
            CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.EDITOR,
            MetronRoleEnum.CONSULTING_EDITOR,
            MetronRoleEnum.ASSISTANT_EDITOR,
            MetronRoleEnum.ASSOCIATE_EDITOR,
            MetronRoleEnum.GROUP_EDITOR,
            MetronRoleEnum.SENIOR_EDITOR,
            MetronRoleEnum.MANAGING_EDITOR,
            MetronRoleEnum.COLLECTION_EDITOR,
            MetronRoleEnum.PRODUCTION,
            MetronRoleEnum.SUPERVISING_EDITOR,
            MetronRoleEnum.EXECUTIVE_EDITOR,
            MetronRoleEnum.EDITOR_IN_CHIEF,
        ),
        ComicInfoRoleTagEnum.INKER: (
            *GenericRoleAliases.INKER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.INKER,
            MetronRoleEnum.INKER,
            MetronRoleEnum.EMBELLISHER,
            MetronRoleEnum.FINISHES,
            MetronRoleEnum.INK_ASSISTS,
            ComicBookInfoRoleEnum.ARTIST,
            MetronRoleEnum.ARTIST,
        ),
        ComicInfoRoleTagEnum.LETTERER: (
            *GenericRoleAliases.LETTERER.value,
            MetronRoleEnum.LETTERER,
        ),
        ComicInfoRoleTagEnum.PENCILLER: (
            *GenericRoleAliases.PENCILLER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.PENCILLER,
            MetronRoleEnum.PENCILLER,
            MetronRoleEnum.BREAKDOWNS,
            MetronRoleEnum.ILLUSTRATOR,
            MetronRoleEnum.LAYOUTS,
            ComicBookInfoRoleEnum.ARTIST,
            MetronRoleEnum.ARTIST,
        ),
        ComicInfoRoleTagEnum.TRANSLATOR: (
            *GenericRoleAliases.TRANSLATOR.value,
            MetronRoleEnum.TRANSLATOR,
        ),
        ComicInfoRoleTagEnum.WRITER: (
            GenericRoleEnum.AUTHOR,
            *GenericRoleAliases.WRITER.value,
            MetronRoleEnum.WRITER,
            MetronRoleEnum.SCRIPT,
            MetronRoleEnum.STORY,
            MetronRoleEnum.PLOT,
            MetronRoleEnum.INTERVIEWER,
        ),
    }
)


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

    _TRANSFORM_KEY_MAP = MappingProxyType(
        {
            "AgeRating": AGE_RATING_KEY,
            # REPRINTS
            # "AlternateCount": ALTERNATE_ISSUE_COUNT_KEY, coded
            # "AlternateNumber": ALTERNATE_ISSUE_KEY, coded
            # "AlternateSeries": ALTERNATE_SERIES_KEY, coded
            #
            "BlackAndWhite": MONOCHROME_KEY,
            "CommunityRating": COMMUNITY_RATING_KEY,
            "Country": COUNTRY_KEY,
            # "Count": ISSUE_COUNT_KEY, coded
            "Day": DAY_KEY,
            # "GTIN": IDENTIFIERS_KEY, coded
            "Format": ORIGINAL_FORMAT_KEY,
            # "Imprint": IMPRINT_KEY, coded
            "LanguageISO": LANGUAGE_KEY,
            "MainCharacterOrTeam": PROTAGONIST_KEY,
            "Manga": "manga",
            "Month": MONTH_KEY,
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
            # "Pages": PAGES_KEY, coded
            # "Publisher": PUBLISHER_KEY coded
            "Review": REVIEW_KEY,
            "ScanInformation": SCAN_INFO_KEY,
            # "Series": SERIES_KEY, coded
            # STORY_ARCS coded
            # "StoryArc":
            # "StoryArcNumber":
            ##
            # "Title": "title", coded
            "Summary": SUMMARY_KEY,
            # "Volume": VOLUME_KEY, coded
            # "Web": WEB_KEY, coded
            "Year": YEAR_KEY,
        }
    )
    _STRINGS_TO_NAMED_OBJS_KEY_MAP = MappingProxyType(
        {
            "Characters": CHARACTERS_KEY,
            "Genre": GENRES_KEY,
            "Locations": LOCATIONS_KEY,
            "SeriesGroup": SERIES_GROUPS_KEY,
            "Tags": TAGS_KEY,
            "Teams": TEAMS_KEY,
        }
    )
    TRANSFORM_MAP = create_transform_map(
        _TRANSFORM_KEY_MAP, _STRINGS_TO_NAMED_OBJS_KEY_MAP
    )
    ROLE_TAGS_ENUM = ComicInfoRoleTagEnum
    ROLE_MAP = create_role_map(ROLE_ALIASES)
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
        ComicInfoStoryArcsTransformMixin.parse_arcs,
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
        XmlCreditsTransformMixin.unparse_credits,
        ComicInfoPagesTransformMixin.unparse_pages,
        ComicInfoReprintsTransformMixin.unparse_reprints,
        ComicInfoStoryArcsTransformMixin.unparse_arcs,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_imprint,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
    )
