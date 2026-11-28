"""CoMet transforms."""

import re
import sys
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict
from loguru import logger

from comicbox.enums.comet import CoMetRoleTagEnum
from comicbox.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.enums.comicinfo import ComicInfoRoleTagEnum
from comicbox.enums.generic.role import GenericRoleAliases, GenericRoleEnum
from comicbox.enums.metroninfo import MetronRoleEnum
from comicbox.formats.base.transforms.base import BaseTransform
from comicbox.formats.base.transforms.identifiers import (
    identifier_transform_from_cb,
    identifiers_transform_to_cb,
)
from comicbox.formats.base.transforms.price import (
    price_transform_from_cb,
    price_transform_to_cb,
)
from comicbox.formats.base.transforms.publishing_tags import (
    PUBLISHER_NAME_KEYPATH,
    SERIES_NAME_KEYPATH,
    VOLUME_NUMBER_KEYPATH,
)
from comicbox.formats.base.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)
from comicbox.formats.base.transforms.xml_credits import (
    xml_credits_transform_from_cb,
    xml_credits_transform_to_cb,
)
from comicbox.formats.comet.schema import CoMetSchema
from comicbox.formats.comet.transform.reprints import (
    comet_reprints_transform_from_cb,
    comet_reprints_transform_to_cb,
)
from comicbox.formats.comicbox.schema import (
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
from comicbox.formats.comicbox.transform import COVER_DATE_KEYPATH, ISSUE_NAME_KEYPATH
from comicbox.formats.comicbox.transform.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.identifiers import DEFAULT_ID_SOURCE

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

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
            # CoMet has no translator tag; writer is its closest credit.
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
ISSUE_TAG = "issue"
TITLE_TAG = "title"
_WHOLE_NUMBER_RE = re.compile(r"\d+")


def _issue_from_cb(issue_name: str) -> str | None:
    """Write a whole issue number, the XSD's xs:nonNegativeInteger, or nothing."""
    return issue_name if _WHOLE_NUMBER_RE.fullmatch(issue_name) else None


def _first_name(names: set[str]) -> set[str]:
    """
    Keep one name, the first in sort order.

    The CoMet XSD allows one coverDesigner, so several cover credits cannot
    all be written. Sort order keeps repeated writes of a book agreeing.
    """
    return {min(names)} if names else names


def _comet_credits_transform_from_cb() -> tuple[MetaSpec, ...]:
    """Write each CoMet credit tag, with a single coverDesigner."""
    cover_designer_tag = CoMetRoleTagEnum.COVER_DESIGNER.value
    return tuple(
        MetaSpec(key_map=metaspec.key_map, spec=(metaspec.spec, _first_name))
        if cover_designer_tag in metaspec.key_map
        else metaspec
        for metaspec in xml_credits_transform_from_cb(CoMetRoleTagEnum, ROLE_ALIASES)
    )


class CoMetTransform(BaseTransform):
    """CoMet transforms."""

    SCHEMA_CLASS = CoMetSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(
            key_map={**SIMPLE_KEYMAP.inverse, ISSUE_NAME_KEYPATH: ISSUE_TAG},
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
        MetaSpec(key_map={ISSUE_TAG: ISSUE_NAME_KEYPATH}, spec=_issue_from_cb),
        name_obj_from_cb(NAME_OBJ_KEY_MAP),
        *_comet_credits_transform_from_cb(),
        identifier_transform_from_cb("identifier"),
        price_transform_from_cb("price"),
        comet_reprints_transform_from_cb("isVersionOf"),
        format_root_keypath=CoMetSchema.ROOT_KEYPATH,
    )

    @override
    def from_comicbox(self, data: Mapping) -> MappingProxyType:
        """Warn when the written CoMet lacks the title its XSD requires."""
        comet = super().from_comicbox(data)
        if not comet.get(CoMetSchema.ROOT_TAG, {}).get(TITLE_TAG):
            logger.warning("Writing CoMet without the title its schema requires.")
        return comet
