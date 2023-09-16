""""Contributors Nested Schema."""
from types import MappingProxyType

from comicbox.fields.collections import StringSetField
from comicbox.schemas.base import BaseSchema


def get_case_credit_map(casefunc):
    """Build a credit key map from a stringcase function."""
    credit_key_map = {}
    keys = ContributorsSchema().fields.keys()
    for key in keys:
        credit_key_map[casefunc(key)] = key
    return MappingProxyType(credit_key_map)


def get_case_contributor_map(contributor_map, casefunc):
    """Build a contributor key map with a stringcase function."""
    case_contributor_map = {}
    for key, variants in contributor_map.items():
        case_variants = frozenset({casefunc(variant) for variant in variants})
        case_contributor_map[casefunc(key)] = case_variants
    return MappingProxyType(case_contributor_map)


def get_role_variant_map(contributor_map):
    """Get a map of variant roles that are *not* in the schema."""
    role_variant_map = {}
    for key, values in contributor_map.items():
        for value in values:
            if value != key:
                role_variant_map[value] = key
    return MappingProxyType(role_variant_map)


class ContributorsSchema(BaseSchema):
    """Contributors."""

    colorist = StringSetField()
    cover_artist = StringSetField()
    creator = StringSetField()
    editor = StringSetField()
    inker = StringSetField()
    letterer = StringSetField()
    penciller = StringSetField()
    writer = StringSetField()
