"""Transforms to and from ComicRack's ComicInfo.xml schema."""

from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COMMUNITY_RATING_KEY,
    COUNTRY_KEY,
    DAY_KEY,
    GENRES_KEY,
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
from comicbox.schemas.comicinfo import ComicInfoSchema
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import ISSUE_NAME_KEYPATH
from comicbox.transforms.comicbox.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.transforms.comicinfo.identifiers import COMICINFO_IDENTIFIERS_TO_CB
from comicbox.transforms.comicinfo.pages import (
    comicinfo_pages_from_cb,
    comicinfo_pages_to_cb,
)
from comicbox.transforms.comicinfo.reprints import (
    COMICINFO_REPRINTS_FROM_CB,
    COMICINFO_REPRINTS_TO_CB,
)
from comicbox.transforms.comicinfo.storyarcs import (
    story_arcs_from_cb,
    story_arcs_to_cb,
)
from comicbox.transforms.identifiers import (
    identifiers_transform_from_cb,
    urls_transform_from_cb,
)
from comicbox.transforms.publishing_tags import (
    IMPRINT_NAME_KEY_PATH,
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)
from comicbox.transforms.stories import (
    stories_key_transform_from_cb,
    stories_key_transform_to_cb,
)
from comicbox.transforms.xml_credits import (
    xml_credits_transform_from_cb,
    xml_credits_transform_to_cb,
)

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

PAGE_KEY_MAP = frozenbidict(
    {
        # IMAGE_ATTRIBUTE: PAGE_INDEX_KEY,
        "@Type": "page_type",
        "@DoublePage": "double_page",
        "@ImageSize": "size",
        "@Key": "key",
        "@Bookmark": "bookmark",
        "@ImageWidth": "width",
        "@ImageHeight": "height",
    }
)
SIMPLE_KEY_MAP = frozenbidict(
    {
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
        "Number": ISSUE_NAME_KEYPATH,
        "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
        "Publisher": PUBLISHER_NAME_KEY_PATH,
        "Review": REVIEW_KEY,
        "ScanInformation": SCAN_INFO_KEY,
        "Series": SERIES_NAME_KEY_PATH,
        "Summary": SUMMARY_KEY,
        "Volume": VOLUME_NUMBER_KEY_PATH,
        "Year": YEAR_KEY,
    }
)
NAME_OBJ_KEY_MAP = frozenbidict(
    {
        "Characters": CHARACTERS_KEY,
        "Genre": GENRES_KEY,
        "Locations": LOCATIONS_KEY,
        "SeriesGroup": SERIES_GROUPS_KEY,
        "Tags": TAGS_KEY,
        "Teams": TEAMS_KEY,
    }
)


class ComicInfoTransform(BaseTransform):
    """ComicInfo.xml Schema."""

    SCHEMA_CLASS = ComicInfoSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP.inverse),
        name_obj_to_cb(NAME_OBJ_KEY_MAP.inverse),
        xml_credits_transform_to_cb(ComicInfoRoleTagEnum),
        COMICINFO_IDENTIFIERS_TO_CB,
        comicinfo_pages_to_cb("Pages.Page", PAGE_KEY_MAP.inverse),
        COMICINFO_REPRINTS_TO_CB,
        stories_key_transform_to_cb("Title"),
        story_arcs_to_cb("StoryArc", "StoryArcNumber"),
        format_root_keypath=ComicInfoSchema.ROOT_KEY_PATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        name_obj_from_cb(NAME_OBJ_KEY_MAP),
        *xml_credits_transform_from_cb(ComicInfoRoleTagEnum, ROLE_ALIASES),
        identifiers_transform_from_cb("GTIN"),
        comicinfo_pages_from_cb("Pages.Page", PAGE_KEY_MAP),
        COMICINFO_REPRINTS_FROM_CB,
        stories_key_transform_from_cb("Title"),
        *story_arcs_from_cb("StoryArc", "StoryArcNumber"),
        urls_transform_from_cb("Web"),
        format_root_keypath=ComicInfoSchema.ROOT_KEY_PATH,
    )
