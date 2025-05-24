"""MetronInfo.xml Transforms for credits."""

from enum import Enum
from types import MappingProxyType

from glom import Assign, glom

from comicbox.fields.enum_fields import EnumField
from comicbox.schemas.comicbox import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.schemas.enums.comet import CoMetRoleTagEnum
from comicbox.schemas.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.enums.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.enums.metroninfo import MetronRoleEnum
from comicbox.schemas.enums.role import GenericRoleAliases, GenericRoleEnum
from comicbox.schemas.metroninfo import CREATOR_TAG
from comicbox.transforms.identifiers import (
    PRIMARY_ID_SOURCE_KEYPATH,
)
from comicbox.transforms.metroninfo.const import DEFAULT_ID_SOURCE
from comicbox.transforms.metroninfo.identified_name import (
    identified_name_from_cb,
    identified_name_to_cb,
)
from comicbox.transforms.metroninfo.identifiers import SCOPE_PRIMARY_SOURCE
from comicbox.transforms.spec import MetaSpec

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

CREDITS_KEYPATH = "Credits.Credit"
ROLE_KEYPATH = "Roles.Role"


def _create_role_variations_to_enum_map(role_aliases):
    """Create role map for variations of a role name to to the native enum value."""
    role_map = {}
    for native_enum, aliases in role_aliases.items():
        key_variations = set()
        all_aliases = (*aliases, native_enum)
        for alias in all_aliases:
            key_variations |= EnumField.get_key_variations(alias)
        for variation in key_variations:
            lower_varation = variation.lower()
            if lower_varation not in role_map:
                role_map[lower_varation] = set()
            role_map[lower_varation].add(native_enum)
    return role_map


def _credit_to_cb(metron_credit, primary_id_source) -> tuple[str, dict]:
    """Copy a single metron style credit entry into comicbox credits."""
    metron_creator = metron_credit.pop(CREATOR_TAG, {})
    person_name, comicbox_credit = identified_name_to_cb(
        metron_creator, "creator", primary_id_source
    )
    if metron_roles := glom(metron_credit, "Roles.Role", default=None):
        for metron_role in metron_roles:
            role_name, comicbox_role = identified_name_to_cb(
                metron_role, "role", primary_id_source
            )
            if role_name:
                glom(
                    comicbox_credit,
                    Assign(f"{ROLES_KEY}.{role_name}", comicbox_role, missing=dict),
                )

    return person_name, comicbox_credit


def _credits_to_cb(values):
    metron_credits = values.get(CREDITS_KEYPATH)
    if not metron_credits:
        return {}
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    return {
        person_credit[0]: person_credit[1]
        for metron_credit in metron_credits
        if (person_credit := _credit_to_cb(metron_credit, primary_id_source))
    }


def _role_from_cb(role_name, comicbox_role, id_source, role_map):
    """Unparse a metron role to an enum only value."""
    metron_roles = []

    if metron_role_enums := role_map.get(role_name.lower()):
        # Handle expanding one role into many.
        metron_role = []
        for metron_role_enum in metron_role_enums:
            metron_role = identified_name_from_cb(
                metron_role_enum, comicbox_role, id_source
            )
            metron_roles.append(metron_role)
    return metron_roles


def _credit_from_cb(
    person_name: str, comicbox_credit: dict, id_source: str, role_map
) -> dict:
    """Aggregate comicbox credits into Metron credit dict."""
    if not person_name:
        return {}
    metron_creator = identified_name_from_cb(person_name, comicbox_credit, id_source)
    metron_credit = {CREATOR_TAG: metron_creator}
    if comicbox_roles := comicbox_credit.get(ROLES_KEY):
        all_metron_roles = []
        for role_name, comicbox_role in comicbox_roles.items():
            metron_roles = _role_from_cb(role_name, comicbox_role, id_source, role_map)
            all_metron_roles.extend(metron_roles)
        glom(metron_credit, Assign(ROLE_KEYPATH, all_metron_roles, missing=dict))
    return metron_credit


def _credits_from_cb(values, role_map):
    comicbox_credits = values.get(CREDITS_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    return [
        metron_credit
        for person_name, comicbox_credit in comicbox_credits.items()
        if (
            metron_credit := _credit_from_cb(
                person_name, comicbox_credit, primary_id_source, role_map
            )
        )
    ]


METRON_CREDITS_TRANSFORM_TO_CB = MetaSpec(
    key_map={CREDITS_KEY: (CREDITS_KEYPATH, SCOPE_PRIMARY_SOURCE)},
    spec=_credits_to_cb,
)


def metron_credits_from_cb():
    """Create credits from cb transform."""
    role_map = _create_role_variations_to_enum_map(ROLE_ALIASES)

    def from_cb(values):
        return _credits_from_cb(values, role_map)

    return MetaSpec(
        key_map={CREDITS_KEYPATH: (CREDITS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
        spec=from_cb,
    )
