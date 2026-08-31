"""Comic Book Info Credits Transform Mixin."""

from enum import Enum
from types import MappingProxyType
from typing import Any

from loguru import logger

from comicbox.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.enums.generic.role import GenericRoleEnum
from comicbox.enums.metroninfo import MetronRoleEnum
from comicbox.formats.base.fields.enum_fields import EnumField
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comic_book_info.schema import (
    PERSON_TAG,
    PRIMARY_TAG,
    ROLE_TAG,
)
from comicbox.formats.comicbox.schema import (
    CREDIT_PRIMARIES_KEY,
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.formats.comicbox.transform.credits import (
    add_credit_role_to_comicbox_credits,
)

# Comicbox stores the Metron role vocabulary, which is far richer than
# ComicBookInfo's ten roles, so writing projects onto CBI's spelling the way
# every other format's transform does. CBI's enum is explicitly "common but
# not restricted to", so a role with no CBI equivalent is written verbatim.
ROLE_ALIASES: MappingProxyType[Enum, tuple[Enum | str, ...]] = MappingProxyType(
    {
        ComicBookInfoRoleEnum.ARTIST: (MetronRoleEnum.ARTIST,),
        ComicBookInfoRoleEnum.COLORER: (
            GenericRoleEnum.COLOURIST,
            MetronRoleEnum.COLORIST,
            MetronRoleEnum.COLOR_SEPARATIONS,
            MetronRoleEnum.COLOR_ASSISTS,
            MetronRoleEnum.COLOR_FLATS,
            MetronRoleEnum.GRAY_TONE,
        ),
        ComicBookInfoRoleEnum.COVER_ARTIST: (MetronRoleEnum.COVER,),
        ComicBookInfoRoleEnum.EDITOR: (
            MetronRoleEnum.EDITOR,
            MetronRoleEnum.CONSULTING_EDITOR,
            MetronRoleEnum.ASSISTANT_EDITOR,
            MetronRoleEnum.ASSOCIATE_EDITOR,
            MetronRoleEnum.GROUP_EDITOR,
            MetronRoleEnum.SENIOR_EDITOR,
            MetronRoleEnum.MANAGING_EDITOR,
            MetronRoleEnum.COLLECTION_EDITOR,
            MetronRoleEnum.SUPERVISING_EDITOR,
            MetronRoleEnum.EXECUTIVE_EDITOR,
            MetronRoleEnum.EDITOR_IN_CHIEF,
        ),
        ComicBookInfoRoleEnum.INKER: (
            MetronRoleEnum.INKER,
            MetronRoleEnum.EMBELLISHER,
            MetronRoleEnum.FINISHES,
            MetronRoleEnum.INK_ASSISTS,
        ),
        ComicBookInfoRoleEnum.LETTERER: (MetronRoleEnum.LETTERER,),
        ComicBookInfoRoleEnum.OTHER: (MetronRoleEnum.OTHER,),
        ComicBookInfoRoleEnum.PENCILLER: (
            MetronRoleEnum.PENCILLER,
            MetronRoleEnum.BREAKDOWNS,
            MetronRoleEnum.ILLUSTRATOR,
            MetronRoleEnum.LAYOUTS,
        ),
        ComicBookInfoRoleEnum.TRANSLATOR: (MetronRoleEnum.TRANSLATOR,),
        ComicBookInfoRoleEnum.WRITER: (
            GenericRoleEnum.AUTHOR,
            MetronRoleEnum.WRITER,
            MetronRoleEnum.SCRIPT,
            MetronRoleEnum.STORY,
            MetronRoleEnum.PLOT,
            MetronRoleEnum.INTERVIEWER,
        ),
    }
)


def _create_cbi_role_map() -> MappingProxyType[str, str]:
    """Map every alias spelling to the CBI role name that covers it."""
    role_map: dict[str, str] = {}
    for cbi_enum, aliases in ROLE_ALIASES.items():
        for alias in (*aliases, cbi_enum):
            for variation in EnumField.get_key_variations(alias):
                role_map[variation] = cbi_enum.value
    return MappingProxyType(role_map)


_CBI_ROLE_MAP = _create_cbi_role_map()


def cbi_role_from_cb(role_name: str) -> str:
    """Project a canonical comicbox role onto ComicBookInfo's vocabulary."""
    for variation in EnumField.get_ordered_key_variations(role_name):
        if cbi_role := _CBI_ROLE_MAP.get(variation):
            return cbi_role
    return role_name


def _get_cbi_credit_parts(cbi_credit: dict[str, str]) -> tuple:
    cbi_person = cbi_credit.get(PERSON_TAG, "")
    cbi_role = cbi_credit.get(ROLE_TAG, "")
    return cbi_person, cbi_role


def _cbi_credits_to_cb(cbi_credits: list[dict[str, str]]) -> dict:
    comicbox_credits = {}
    for cbi_credit in cbi_credits:
        try:
            cbi_person, cbi_role = _get_cbi_credit_parts(cbi_credit)
            add_credit_role_to_comicbox_credits(cbi_person, cbi_role, comicbox_credits)
        except Exception as exc:
            logger.warning(f"Parsing credit {cbi_credit}: {exc}")
    return comicbox_credits


def cbi_credits_transform_to_cb(credits_tag: str) -> MetaSpec:
    """Transform for CBI credits."""
    return MetaSpec(
        key_map={CREDITS_KEY: credits_tag},
        spec=_cbi_credits_to_cb,
    )


def _cbi_credits_primary_to_cb(cbi_credits: list[dict[str, str]]) -> dict:
    credit_primaries = {}
    for cbi_credit in cbi_credits:
        if cbi_credit.get(PRIMARY_TAG):
            cbi_person, cbi_role = _get_cbi_credit_parts(cbi_credit)
            credit_primaries[cbi_role] = cbi_person
    return credit_primaries


def cbi_credits_primary_to_cb(credits_tag: str) -> MetaSpec:
    """Transform the credit primaries key from cbi credits."""
    return MetaSpec(
        key_map={CREDIT_PRIMARIES_KEY: credits_tag}, spec=_cbi_credits_primary_to_cb
    )


def _cbi_credit_from_cb(
    person_name: str,
    comicbox_credit: dict[str, Any],
    cbi_credits: list[Any],
    credit_primaries: Any,
) -> None:
    """Unparse one comicbox credit into cbi credits."""
    if not person_name:
        return
    comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
    for role_name in comicbox_roles:
        cbi_role = cbi_role_from_cb(role_name)
        cbi_credit: dict[str, Any] = {PERSON_TAG: person_name, ROLE_TAG: cbi_role}
        if credit_primaries and credit_primaries.get(role_name) == person_name:
            cbi_credit[PRIMARY_TAG] = True
        cbi_credits.append(cbi_credit)


def _cbi_credits_from_cb(
    values: dict[str, Any],
) -> list:
    comicbox_credits = values.get(CREDITS_KEY)
    credit_primaries = values.get(CREDIT_PRIMARIES_KEY)
    cbi_credits = []
    if not comicbox_credits:
        return cbi_credits
    for person_name, comicbox_credit in comicbox_credits.items():
        try:
            _cbi_credit_from_cb(
                person_name, comicbox_credit, cbi_credits, credit_primaries
            )
        except Exception as exc:
            logger.warning(f"Unparsing credit {comicbox_credit} - {exc}")
            logger.exception("debug")
    return cbi_credits


def cbi_credits_transform_from_cb(credits_tag: str) -> MetaSpec:
    """Transform for CBI credits."""
    return MetaSpec(
        key_map={credits_tag: (CREDITS_KEY, CREDIT_PRIMARIES_KEY)},
        spec=_cbi_credits_from_cb,
    )
