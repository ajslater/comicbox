"""CoMet transforms."""

from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.identifiers import DEFAULT_ID_SOURCE
from comicbox.schemas.comet import CoMetSchema
from comicbox.schemas.comicbox import (
    AGE_RATING_KEY,
    BOOKMARK_KEY,
    CHARACTERS_KEY,
    COVER_IMAGE_KEY,
    GENRES_KEY,
    LANGUAGE_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    READING_DIRECTION_KEY,
    RIGHTS_KEY,
    SUMMARY_KEY,
    TITLE_KEY,
)
from comicbox.schemas.enums.comet import CoMetRoleTagEnum
from comicbox.schemas.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.enums.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.enums.metroninfo import MetronRoleEnum
from comicbox.schemas.enums.role import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet.reprints import (
    comet_reprints_transform_from_cb,
    comet_reprints_transform_to_cb,
)
from comicbox.transforms.comicbox import COVER_DATE_KEYPATH, ISSUE_NAME_KEYPATH
from comicbox.transforms.comicbox.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.transforms.identifiers import (
    identifiers_transform_from_cb,
    identifiers_transform_to_cb,
)
from comicbox.transforms.price import (
    price_transform_from_cb,
    price_transform_to_cb,
)
from comicbox.transforms.publishing_tags import (
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
        CoMetRoleTagEnum.COLORIST: (
            GenericRoleEnum.COLOURIST,
            *GenericRoleAliases.COLORIST.value,
            *GenericRoleAliases.PAINTER.value,
            ComicInfoRoleTagEnum.COLORIST,
            MetronRoleEnum.COLORIST,
            MetronRoleEnum.COLOR_SEPARATIONS,
            MetronRoleEnum.COLOR_ASSISTS,
            MetronRoleEnum.COLOR_FLATS,
            MetronRoleEnum.GRAY_TONE,
        ),
        CoMetRoleTagEnum.COVER_DESIGNER: (
            *GenericRoleAliases.COVER.value,
            ComicInfoRoleTagEnum.COVER_ARTIST,
            MetronRoleEnum.COVER,
        ),
        CoMetRoleTagEnum.CREATOR: (),
        CoMetRoleTagEnum.EDITOR: (
            *GenericRoleAliases.EDITOR.value,
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
        CoMetRoleTagEnum.INKER: (
            *GenericRoleAliases.INKER.value,
            *GenericRoleAliases.PAINTER.value,
            ComicInfoRoleTagEnum.INKER,
            MetronRoleEnum.INKER,
            MetronRoleEnum.EMBELLISHER,
            MetronRoleEnum.FINISHES,
            MetronRoleEnum.INK_ASSISTS,
            ComicBookInfoRoleEnum.ARTIST,
            MetronRoleEnum.ARTIST,
        ),
        CoMetRoleTagEnum.LETTERER: (
            *GenericRoleAliases.LETTERER.value,
            ComicInfoRoleTagEnum.LETTERER,
            MetronRoleEnum.LETTERER,
        ),
        CoMetRoleTagEnum.PENCILLER: (
            *GenericRoleAliases.PENCILLER.value,
            *GenericRoleAliases.PAINTER.value,
            ComicBookInfoRoleEnum.ARTIST,
            MetronRoleEnum.ARTIST,
            ComicInfoRoleTagEnum.PENCILLER,
            MetronRoleEnum.PENCILLER,
            MetronRoleEnum.BREAKDOWNS,
            MetronRoleEnum.ILLUSTRATOR,
            MetronRoleEnum.LAYOUTS,
        ),
        CoMetRoleTagEnum.WRITER: (
            GenericRoleEnum.AUTHOR,
            *GenericRoleAliases.WRITER.value,
            MetronRoleEnum.WRITER,
            MetronRoleEnum.SCRIPT,
            MetronRoleEnum.STORY,
            MetronRoleEnum.PLOT,
            MetronRoleEnum.INTERVIEWER,
            MetronRoleEnum.WRITER,
            MetronRoleEnum.SCRIPT,
            MetronRoleEnum.STORY,
            MetronRoleEnum.PLOT,
            MetronRoleEnum.INTERVIEWER,
            MetronRoleEnum.TRANSLATOR,
        ),
    }
)
SIMPLE_KEYMAP = frozenbidict(
    {
        "coverImage": COVER_IMAGE_KEY,
        "date": COVER_DATE_KEYPATH,
        "description": SUMMARY_KEY,
        "format": ORIGINAL_FORMAT_KEY,
        "issue": ISSUE_NAME_KEYPATH,
        "language": LANGUAGE_KEY,
        "lastMark": BOOKMARK_KEY,
        "pages": PAGE_COUNT_KEY,
        "publisher": PUBLISHER_NAME_KEYPATH,
        "rating": AGE_RATING_KEY,
        "readingDirection": READING_DIRECTION_KEY,
        "rights": RIGHTS_KEY,
        "series": SERIES_NAME_KEYPATH,
        "title": TITLE_KEY,
        "volume": VOLUME_NUMBER_KEYPATH,
    }
)
NAME_OBJ_KEY_MAP = frozenbidict({"character": CHARACTERS_KEY, "genre": GENRES_KEY})


class CoMetTransform(BaseTransform):
    """CoMet transforms."""

    SCHEMA_CLASS = CoMetSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(
            key_map=SIMPLE_KEYMAP.inverse,
        ),
        name_obj_to_cb(NAME_OBJ_KEY_MAP.inverse),
        xml_credits_transform_to_cb(CoMetRoleTagEnum),
        identifiers_transform_to_cb("identifier", DEFAULT_ID_SOURCE),
        price_transform_to_cb("price"),
        comet_reprints_transform_to_cb("isVersionOf"),
        format_root_keypath=CoMetSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEYMAP),
        name_obj_from_cb(NAME_OBJ_KEY_MAP),
        *xml_credits_transform_from_cb(CoMetRoleTagEnum, ROLE_ALIASES),
        identifiers_transform_from_cb("identifier"),
        price_transform_from_cb("price"),
        comet_reprints_transform_from_cb("isVersionOf"),
        format_root_keypath=CoMetSchema.ROOT_KEYPATH,
    )
