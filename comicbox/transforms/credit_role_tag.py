"""Credit Roles defined as Tags."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from comicbox.fields.enum_fields import EnumField


def create_role_map(
    role_aliases: Mapping[Enum, tuple[Enum | str, ...]],
) -> MappingProxyType[str, tuple[Enum, ...]]:
    """Convert the PRE_ROLE_MAP into the ROLE_MAP."""
    role_map = {}
    for native_enum, aliases in role_aliases.items():
        key_variations = set()
        all_aliases = (*aliases, native_enum)
        for alias in all_aliases:
            key_variations |= EnumField.get_key_variations(alias)
        for key_varation in key_variations:
            roles = role_map.get(key_varation, set())
            roles.add(native_enum)
            role_map[key_varation] = roles
    return MappingProxyType({key: tuple(value) for key, value in role_map.items()})


def get_role_enums(role_map: Mapping, comicbox_role_name: str) -> tuple[Enum, ...]:
    """Get a this transform's role enums for a comicbox role name."""
    comicbox_role_name = comicbox_role_name if comicbox_role_name else ""
    lower_role_name = comicbox_role_name.lower()
    return role_map.get(lower_role_name, ())
