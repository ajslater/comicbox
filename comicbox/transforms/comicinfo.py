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
    PAGE_INDEX_KEY,
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
from comicbox.transforms.base import name_obj_to_string_list_key_transforms
from comicbox.transforms.comicinfo_pages import comicinfo_pages_transform
from comicbox.transforms.comicinfo_reprints import (
    ComicInfoReprintsTransformMixin,
)
from comicbox.transforms.comicinfo_storyarcs import story_arcs_transform
from comicbox.transforms.credit_role_tag import (
    create_role_map,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.publishing_tags import (
    IMPRINT_NAME_KEY_PATH,
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
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


_PAGE_TRANSFORM_MAP = create_transform_map(
    KeyTransforms(
        key_map={
            "@Image": PAGE_INDEX_KEY,
            "@Type": "page_type",
            "@DoublePage": "double_page",
            "@ImageSize": "size",
            "@Key": "key",
            "@Bookmark": "bookmark",
            "@ImageWidth": "width",
            "@ImageHeight": "height",
        }
    )
)


class ComicInfoTransform(
    ComicInfoReprintsTransformMixin,
    IdentifiersTransformMixin,
    XmlCreditsTransformMixin,
):
    """ComicInfo.xml Schema."""

    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "AgeRating": AGE_RATING_KEY,
                "BlackAndWhite": MONOCHROME_KEY,
                "CommunityRating": COMMUNITY_RATING_KEY,
                "Country": COUNTRY_KEY,
                "Count": ISSUE_COUNT_KEY_PATH,
                "Day": DAY_KEY,
                "Format": ORIGINAL_FORMAT_KEY,
                "Imprint": IMPRINT_NAME_KEY_PATH,
                "LanguageISO": LANGUAGE_KEY,
                "MainCharacterOrTeam": PROTAGONIST_KEY,
                "Manga": "manga",
                "Month": MONTH_KEY,
                "Notes": NOTES_KEY,
                "Number": ISSUE_KEY,
                "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
                "Publisher": PUBLISHER_NAME_KEY_PATH,
                "Review": REVIEW_KEY,
                "ScanInformation": SCAN_INFO_KEY,
                "Series": SERIES_NAME_KEY_PATH,
                "Summary": SUMMARY_KEY,
                "Volume": VOLUME_NUMBER_KEY_PATH,
                "Year": YEAR_KEY,
                # COPY from old transforms
                **{
                    key: key
                    for key in {  # "arcs",
                        "credits",
                        "identifiers",
                        "reprints",
                    }
                    | {
                        "AlternateSeries",
                        "AlternateNumber",
                        "AlternateCount",
                        "GTIN",
                        # "StoryArc",
                        # "StoryArcNumber",
                        "Title",
                        "Web",
                        "Writer",
                        "Penciller",
                        "Inker",
                        "Colorist",
                        "Letterer",
                        "CoverArtist",
                        "Editor",
                        "Translator",
                    }
                },
            }
        ),
        name_obj_to_string_list_key_transforms(
            {
                "Characters": CHARACTERS_KEY,
                "Genre": GENRES_KEY,
                "Locations": LOCATIONS_KEY,
                "SeriesGroup": SERIES_GROUPS_KEY,
                "Tags": TAGS_KEY,
                "Teams": TEAMS_KEY,
            }
        ),
        comicinfo_pages_transform(_PAGE_TRANSFORM_MAP),
        stories_key_transform("Title"),
        story_arcs_transform("StoryArc", "StoryArcNumber"),
    )
    ROLE_TAGS_ENUM = ComicInfoRoleTagEnum
    ROLE_MAP = create_role_map(ROLE_ALIASES)
    SCHEMA_CLASS = ComicInfoSchema
    IDENTIFIERS_TAG = GTIN_TAG
    NAKED_NID = GTIN_NID
    URLS_TAG = "Web"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.parse_credits,
        ComicInfoReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.unparse_credits,
        ComicInfoReprintsTransformMixin.unparse_reprints,
        IdentifiersTransformMixin.unparse_identifiers,
    )
