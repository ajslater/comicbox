"""CoMet transforms."""

from enum import Enum
from types import MappingProxyType

from comicbox.identifiers import COMICVINE_NID
from comicbox.schemas.comet import (
    CoMetRoleTagEnum,
    CoMetSchema,
)
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COVER_IMAGE_KEY,
    DATE_KEY,
    GENRES_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LAST_MARK_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    READING_DIRECTION_KEY,
    RIGHTS_KEY,
    SUMMARY_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet.reprints import comet_reprints_transform
from comicbox.transforms.comicbox.name_objs import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.credit_role import create_role_map
from comicbox.transforms.identifiers import identifiers_transform
from comicbox.transforms.price import price_key_transform
from comicbox.transforms.publishing_tags import (
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.transforms.xml_credits import xml_credits_transform

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


class CoMetTransform(BaseTransform):
    """CoMet transforms."""

    SCHEMA_CLASS = CoMetSchema
    ROLE_MAP = create_role_map(ROLE_ALIASES)
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "coverImage": COVER_IMAGE_KEY,
                "date": DATE_KEY,
                "description": SUMMARY_KEY,
                "format": ORIGINAL_FORMAT_KEY,
                "issue": ISSUE_KEY,
                "language": LANGUAGE_KEY,
                "lastMark": LAST_MARK_KEY,
                "pages": PAGE_COUNT_KEY,
                "publisher": PUBLISHER_NAME_KEY_PATH,
                "rating": AGE_RATING_KEY,
                "readingDirection": READING_DIRECTION_KEY,
                "rights": RIGHTS_KEY,
                "series": SERIES_NAME_KEY_PATH,
                "volume": VOLUME_NUMBER_KEY_PATH,
            }
        ),
        name_obj_to_string_list_key_transforms(
            {"character": CHARACTERS_KEY, "genre": GENRES_KEY},
        ),
        xml_credits_transform(CoMetRoleTagEnum, ROLE_MAP, CoMetSchema.ROOT_TAG),
        identifiers_transform("identifier", COMICVINE_NID),
        price_key_transform("price"),
        comet_reprints_transform("isVersionOf"),
        stories_key_transform("title"),
        format_root_key_path=CoMetSchema.ROOT_KEY_PATH,
    )
