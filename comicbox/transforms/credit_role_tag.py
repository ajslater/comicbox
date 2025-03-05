"""Credit Roles defined as Tags."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from comicbox.fields.enum_fields import EnumField
from comicbox.transforms.base import BaseTransform


class GenericRoleAliases(Enum):
    """Generic Role Aliases."""

    COLORIST = (
        "colourist",
        "colorer",
        "colourer",
        "colors",
        "colours",
        "painting",
        "painter",
    )
    COVER = ("covers",)
    EDITOR = ("edits", "editing")
    INKER = ("finishes", "inks", "painting", "painter")
    LETTERER = ("letters",)
    PENCILLER = ("breakdowns", "pencils", "painting", "painter")
    TRANSLATOR = ("translation",)
    WRITER = ("plotter", "scripter", "script", "author")


def create_role_map(
    role_aliases: Mapping[Enum, tuple[Enum | str, ...]],
) -> MappingProxyType[str, tuple[Enum, ...]]:
    """Convert the PRE_ROLE_MAP into the ROLE_MAP."""
    role_map = {}
    for native_enum, aliases in role_aliases.items():
        key_variations = set()
        for alias in aliases:
            key_variations |= EnumField.get_key_variations(alias)
        for key_varation in key_variations:
            roles = role_map.get(key_varation, set())
            roles.add(native_enum)
            role_map[key_varation] = roles
    return MappingProxyType({key: tuple(value) for key, value in role_map.items()})


class CreditRoleTagTransformMixin(BaseTransform):
    """Credit Roles defined as Tags."""

    ROLE_MAP: MappingProxyType[str, tuple[Enum, ...]] = MappingProxyType({})

    @classmethod
    def get_role_enums(cls, comicbox_role_name: str) -> tuple[Enum, ...]:
        """Get a this transform's role enums for a comicbox role name."""
        if not comicbox_role_name:
            return ()
        lower_role_name = comicbox_role_name.lower()
        return cls.ROLE_MAP.get(lower_role_name, ())
