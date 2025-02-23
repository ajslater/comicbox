"""Credit Roles defined as Tags."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from comicbox.transforms.base import BaseTransform


def create_role_map(pre_role_map: Mapping[Enum, Enum | tuple[Enum, ...] | None]):
    """Convert the PRE_ROLE_MAP into the ROLE_MAP."""
    role_map = {}
    for from_enum, to_enum in pre_role_map.items():
        key = from_enum.value.lower()
        if not to_enum:
            value = None
        elif isinstance(to_enum, tuple):
            value = tuple(e.value for e in to_enum)
        else:
            value = to_enum.value
        role_map[key] = value
    return MappingProxyType(role_map)


class CreditRoleTagTransformMixin(BaseTransform):
    """Credit Roles defined as Tags."""

    PRE_ROLE_MAP: Mapping[Enum, Enum | tuple[Enum, ...]] = MappingProxyType({})

    ROLE_MAP: MappingProxyType[str, str | tuple[str, ...]] = create_role_map(
        PRE_ROLE_MAP
    )
