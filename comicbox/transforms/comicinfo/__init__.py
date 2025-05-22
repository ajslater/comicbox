"""Transforms to and from ComicRack's ComicInfo.xml schema."""

from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COUNTRY_KEY,
    CRITICAL_RATING_KEY,
    GENRES_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    MANGA_KEY,
    MONOCHROME_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_BOOKMARK_KEY,
    PAGE_COUNT_KEY,
    PAGE_INDEX_KEY,
    PAGE_TYPE_KEY,
    PROTAGONIST_KEY,
    REVIEW_KEY,
    SCAN_INFO_KEY,
    SERIES_GROUPS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    TITLE_KEY,
)
from comicbox.schemas.comicinfo import (
    BOOKMARK_ATTRIBUTE,
    IMAGE_ATTRIBUTE,
    ComicInfoSchema,
)
from comicbox.schemas.enums.comet import CoMetRoleTagEnum
from comicbox.schemas.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.enums.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.enums.metroninfo import MetronRoleEnum
from comicbox.schemas.enums.role import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import (
    DAY_KEYPATH,
    ISSUE_NAME_KEYPATH,
    MONTH_KEYPATH,
    YEAR_KEYPATH,
)
from comicbox.transforms.comicbox.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.transforms.comicinfo.identifiers import COMICINFO_IDENTIFIERS_TO_CB
from comicbox.transforms.comicinfo.pages import (
    comicinfo_bookmark_to_cb,
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
    IMPRINT_NAME_KEYPATH,
    ISSUE_COUNT_KEYPATH,
    PUBLISHER_NAME_KEYPATH,
    SERIES_NAME_KEYPATH,
    VOLUME_NUMBER_KEYPATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
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
        IMAGE_ATTRIBUTE: PAGE_INDEX_KEY,
        "@Type": PAGE_TYPE_KEY,
        "@DoublePage": "double_page",
        "@ImageSize": "size",
        "@Key": "key",
        BOOKMARK_ATTRIBUTE: PAGE_BOOKMARK_KEY,
        "@ImageWidth": "width",
        "@ImageHeight": "height",
    }
)
SIMPLE_KEY_MAP = frozenbidict(
    {
        "AgeRating": AGE_RATING_KEY,
        "BlackAndWhite": MONOCHROME_KEY,
        "CommunityRating": CRITICAL_RATING_KEY,
        "Country": COUNTRY_KEY,
        "Count": ISSUE_COUNT_KEYPATH,
        "Day": DAY_KEYPATH,
        "Format": ORIGINAL_FORMAT_KEY,
        "Imprint": IMPRINT_NAME_KEYPATH,
        "LanguageISO": LANGUAGE_KEY,
        "MainCharacterOrTeam": PROTAGONIST_KEY,
        "Manga": MANGA_KEY,
        "Month": MONTH_KEYPATH,
        "Notes": NOTES_KEY,
        "Number": ISSUE_NAME_KEYPATH,
        "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
        "Publisher": PUBLISHER_NAME_KEYPATH,
        "Review": REVIEW_KEY,
        "ScanInformation": SCAN_INFO_KEY,
        "Series": SERIES_NAME_KEYPATH,
        "Summary": SUMMARY_KEY,
        "Title": TITLE_KEY,
        "Volume": VOLUME_NUMBER_KEYPATH,
        "Year": YEAR_KEYPATH,
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
        comicinfo_bookmark_to_cb("Pages.Page", BOOKMARK_ATTRIBUTE, IMAGE_ATTRIBUTE),
        COMICINFO_REPRINTS_TO_CB,
        story_arcs_to_cb("StoryArc", "StoryArcNumber"),
        format_root_keypath=ComicInfoSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        name_obj_from_cb(NAME_OBJ_KEY_MAP),
        *xml_credits_transform_from_cb(ComicInfoRoleTagEnum, ROLE_ALIASES),
        identifiers_transform_from_cb("GTIN"),
        comicinfo_pages_from_cb("Pages.Page", PAGE_KEY_MAP),
        COMICINFO_REPRINTS_FROM_CB,
        *story_arcs_from_cb("StoryArc", "StoryArcNumber"),
        urls_transform_from_cb("Web"),
        format_root_keypath=ComicInfoSchema.ROOT_KEYPATH,
    )
