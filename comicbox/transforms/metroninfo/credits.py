"""MetronInfo.xml Transforms for credits."""

from enum import Enum
from types import MappingProxyType

from glom import Assign, glom

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo import CREATOR_TAG
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.credit_role_tag import create_role_map, get_role_enums
from comicbox.transforms.metroninfo.identified_name import (
    identified_name_from_cb,
    identified_name_to_cb,
)
from comicbox.transforms.transform_map import KeyTransforms

ROLE_ALIASES: MappingProxyType[Enum, tuple[Enum | str, ...]] = MappingProxyType(
    {
        MetronRoleEnum.ARTIST: (ComicBookInfoRoleEnum.ARTIST,),
        MetronRoleEnum.ASSISTANT_EDITOR: (),
        MetronRoleEnum.ASSOCIATE_EDITOR: (),
        MetronRoleEnum.BREAKDOWNS: (),
        MetronRoleEnum.CHIEF_CREATIVE_OFFICER: (CoMetRoleTagEnum.CREATOR,),
        MetronRoleEnum.COLLECTION_EDITOR: (),
        MetronRoleEnum.COLORIST: (
            GenericRoleEnum.COLOURIST,
            *GenericRoleAliases.COLORIST.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.COLORIST,
            ComicInfoRoleTagEnum.COLORIST,
        ),
        MetronRoleEnum.COLOR_ASSISTS: (),
        MetronRoleEnum.COLOR_FLATS: (),
        MetronRoleEnum.COLOR_SEPARATIONS: (),
        MetronRoleEnum.CONSULTING_EDITOR: (),
        MetronRoleEnum.COVER: (
            *GenericRoleAliases.COVER.value,
            CoMetRoleTagEnum.COVER_DESIGNER,
            ComicInfoRoleTagEnum.COVER_ARTIST,
        ),
        MetronRoleEnum.DESIGNER: (),
        MetronRoleEnum.DIGITAL_ART_TECHNICIAN: (),
        MetronRoleEnum.EDITOR: (
            *GenericRoleAliases.EDITOR.value,
            CoMetRoleTagEnum.EDITOR,
            ComicInfoRoleTagEnum.EDITOR,
        ),
        MetronRoleEnum.EDITOR_IN_CHIEF: (),
        MetronRoleEnum.EMBELLISHER: (),
        MetronRoleEnum.EXECUTIVE_EDITOR: (),
        MetronRoleEnum.EXECUTIVE_PRODUCER: (),
        MetronRoleEnum.FINISHES: (),
        MetronRoleEnum.GRAY_TONE: (),
        MetronRoleEnum.GROUP_EDITOR: (),
        MetronRoleEnum.ILLUSTRATOR: (),
        MetronRoleEnum.INKER: (
            *GenericRoleAliases.INKER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.INKER,
            ComicInfoRoleTagEnum.INKER,
        ),
        MetronRoleEnum.INK_ASSISTS: (),
        MetronRoleEnum.INTERVIEWER: (),
        MetronRoleEnum.LAYOUTS: (),
        MetronRoleEnum.LETTERER: (
            *GenericRoleAliases.LETTERER.value,
            CoMetRoleTagEnum.LETTERER,
            ComicInfoRoleTagEnum.LETTERER,
        ),
        MetronRoleEnum.LOGO_DESIGN: (),
        MetronRoleEnum.MANAGING_EDITOR: (),
        MetronRoleEnum.OTHER: (ComicBookInfoRoleEnum.OTHER,),
        MetronRoleEnum.PENCILLER: (
            *GenericRoleAliases.PENCILLER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.PENCILLER,
            ComicInfoRoleTagEnum.PENCILLER,
        ),
        MetronRoleEnum.PLOT: (),
        MetronRoleEnum.PRESIDENT: (),
        MetronRoleEnum.PRODUCTION: (),
        MetronRoleEnum.PUBLISHER: (),
        MetronRoleEnum.SCRIPT: (),
        MetronRoleEnum.SENIOR_EDITOR: (),
        MetronRoleEnum.STORY: (),
        MetronRoleEnum.SUPERVISING_EDITOR: (),
        MetronRoleEnum.TRANSLATOR: (
            *GenericRoleAliases.TRANSLATOR.value,
            ComicInfoRoleTagEnum.TRANSLATOR,
        ),
        MetronRoleEnum.WRITER: (
            GenericRoleEnum.AUTHOR,
            *GenericRoleAliases.WRITER.value,
            CoMetRoleTagEnum.WRITER,
            ComicInfoRoleTagEnum.WRITER,
        ),
    }
)

ROLE_MAP = create_role_map(ROLE_ALIASES)
ROLE_KEY_PATH = "Roles.Role"


def _credit_to_cb(source_data: dict, metron_credit) -> tuple[str, dict]:
    """Copy a single metron style credit entry into comicbox credits."""
    metron_creator = metron_credit.pop(CREATOR_TAG, {})
    person_name, comicbox_credit = identified_name_to_cb(
        source_data, metron_creator, "creator"
    )
    if metron_roles := glom(metron_credit, "Roles.Role", default=None):
        for metron_role in metron_roles:
            role_name, comicbox_role = identified_name_to_cb(
                source_data, metron_role, "role"
            )
            if role_name:
                glom(
                    comicbox_credit,
                    Assign(f"{ROLES_KEY}.{role_name}", comicbox_role, missing=dict),
                )

    return person_name, comicbox_credit


def _credits_to_cb(source_data, metron_credits):
    return {
        person_credit[0]: person_credit[1]
        for metron_credit in metron_credits
        if (person_credit := _credit_to_cb(source_data, metron_credit))
    }


def _role_from_cb(source_data, role_name, comicbox_role):
    """Unparse a metron role to an enum only value."""
    metron_roles = []
    if metron_role_enums := get_role_enums(ROLE_MAP, role_name):
        # Handle expanding one role into many.
        metron_role = []
        for metron_role_enum in metron_role_enums:
            metron_role = identified_name_from_cb(
                source_data, metron_role_enum, comicbox_role
            )
            metron_roles.append(metron_role)
    return metron_roles


def _credit_from_cb(source_data: dict, person_name: str, comicbox_credit: dict) -> dict:
    """Aggregate comicbox credits into Metron credit dict."""
    if not person_name:
        return {}
    metron_creator = identified_name_from_cb(source_data, person_name, comicbox_credit)
    metron_credit = {CREATOR_TAG: metron_creator}
    if comicbox_roles := comicbox_credit.get(ROLES_KEY):
        all_metron_roles = []
        for role_name, comicbox_role in comicbox_roles.items():
            metron_roles = _role_from_cb(source_data, role_name, comicbox_role)
            all_metron_roles.extend(metron_roles)
        glom(metron_credit, Assign(ROLE_KEY_PATH, all_metron_roles, missing=dict))
    return metron_credit


def _credits_from_cb(source_data, comicbox_credits):
    return [
        metron_credit
        for person_name, comicbox_credit in comicbox_credits.items()
        if (metron_credit := _credit_from_cb(source_data, person_name, comicbox_credit))
    ]


METRON_CREDITS_TRANSFORM = KeyTransforms(
    key_map={"Credits.Credit": CREDITS_KEY},
    to_cb=_credits_to_cb,
    from_cb=_credits_from_cb,
)
