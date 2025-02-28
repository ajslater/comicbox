"""Credit Roles defined as Tags."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

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
    COVER = ("covers", "coverartist", "coverdesigner")
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
        for alias in aliases:
            alias_str = alias if isinstance(alias, str) else alias.value
            lower_alias_str = alias_str.lower()
            roles = role_map.get(lower_alias_str, set())
            roles.add(native_enum)
            role_map[lower_alias_str] = roles
    return MappingProxyType({key: tuple(value) for key, value in role_map.items()})


class CreditRoleTagTransformMixin(BaseTransform):
    """Credit Roles defined as Tags."""

    ROLE_MAP: MappingProxyType[str, tuple[Enum, ...]] = MappingProxyType({})
