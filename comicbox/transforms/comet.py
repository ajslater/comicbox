"""CoMet transforms."""

from enum import Enum
from types import MappingProxyType

from stringcase import camelcase

from comicbox.schemas.comet import (
    IDENTIFIER_TAG,
    IS_VERSION_OF_TAG,
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
from comicbox.transforms.base import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.comet_reprints import comet_reprints_transform
from comicbox.transforms.credit_role_tag import (
    CreditRoleTagTransformMixin,
    create_role_map,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.price import price_key_transform
from comicbox.transforms.publishing_tags import (
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


class CoMetTransform(
    XmlTransform,
    XmlCreditsTransformMixin,
    IdentifiersTransformMixin,
    CreditRoleTagTransformMixin,
):
    """CoMet transforms."""

    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "coverImage": COVER_IMAGE_KEY,
                "date": DATE_KEY,
                "description": SUMMARY_KEY,
                "format": ORIGINAL_FORMAT_KEY,
                "language": LANGUAGE_KEY,
                "lastMark": LAST_MARK_KEY,
                "pages": PAGE_COUNT_KEY,
                "publisher": PUBLISHER_NAME_KEY_PATH,
                "rating": AGE_RATING_KEY,
                "readingDirection": READING_DIRECTION_KEY,
                "rights": RIGHTS_KEY,
                "series": SERIES_NAME_KEY_PATH,
                "volume": VOLUME_NUMBER_KEY_PATH,
                # COPY from old transform
                **{
                    key: key
                    for key in {
                        "credits",
                        "identifiers",
                        "issue",
                        "issue_number",
                    }
                    | {
                        "identifier",
                        "colorist",
                        "coverDesigner",
                        "creator",
                        "editor",
                        "inker",
                        "letterer",
                        "penciller",
                        "writer",
                    }
                },
            }
        ),
        name_obj_to_string_list_key_transforms(
            {"character": CHARACTERS_KEY, "genre": GENRES_KEY},
        ),
        price_key_transform("price"),
        comet_reprints_transform("isVersionOf"),
        stories_key_transform("title"),
    )
    ROLE_TAGS_ENUM = CoMetRoleTagEnum
    ROLE_MAP = create_role_map(ROLE_ALIASES)

    SCHEMA_CLASS = CoMetSchema
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.parse_credits,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
    )
    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.unparse_credits,
        IdentifiersTransformMixin.unparse_identifiers,
    )

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return camelcase(data)
