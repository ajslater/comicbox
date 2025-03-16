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
    GENRES_KEY,
    LAST_MARK_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    READING_DIRECTION_KEY,
    SUMMARY_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import name_obj_to_string_list, string_list_to_name_obj
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.credit_role_tag import (
    CreditRoleTagTransformMixin,
    create_role_map,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.price_mixin import PriceTransformMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
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
    CoMetReprintsTransformMixin,
    NestedPublishingTagsMixin,
    IdentifiersTransformMixin,
    TitleStoriesMixin,
    PriceTransformMixin,
    CreditRoleTagTransformMixin,
):
    """CoMet transforms."""

    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "coverImage": COVER_IMAGE_KEY,
                # "date": "date", handled by code
                "description": SUMMARY_KEY,
                "format": ORIGINAL_FORMAT_KEY,
                # IDENTIFIER_TAG: "identifiers", handled by code
                # "language": LANGUAGE_KEY, handled by code
                "lastMark": LAST_MARK_KEY,
                "pages": PAGE_COUNT_KEY,
                # "publisher": "publisher", handled by code
                # "price": PRICES_KEY coded
                "rating": AGE_RATING_KEY,
                "readingDirection": READING_DIRECTION_KEY,
                # "rights": "rights", unused
                # "series": SERIES_KEY,  handled by code
                # "title": "title", handled by code
                # "volume": VOLUME_KEY, handled by code
            }
        ),
        KeyTransforms(
            key_map={"character": CHARACTERS_KEY, "genre": GENRES_KEY},
            to_cb=string_list_to_name_obj,
            from_cb=name_obj_to_string_list,
        ),
    )
    ROLE_TAGS_ENUM = CoMetRoleTagEnum
    ROLE_MAP = create_role_map(ROLE_ALIASES)

    SCHEMA_CLASS = CoMetSchema
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None
    PUBLISHER_TAG = "publisher"
    SERIES_TAG = "series"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = ""
    TITLE_TAG = "title"
    PRICE_TAG = "price"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.parse_credits,
        CoMetReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
        PriceTransformMixin.parse_price,
    )
    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.unparse_credits,
        CoMetReprintsTransformMixin.unparse_reprints,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        PriceTransformMixin.unparse_price,
    )

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return camelcase(data)
