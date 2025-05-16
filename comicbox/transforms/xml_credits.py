"""XML Credits Mixin."""

from loguru import logger

from comicbox.fields.enum_fields import EnumField
from comicbox.schemas.comicbox import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.transforms.comicbox.credits import add_credit_role_to_comicbox_credits
from comicbox.transforms.spec import MetaSpec


def _create_role_enum_to_alias_map(role_aliases):
    """Create role map for native enum value to a list of aliases."""
    role_map = {}
    for native_enum, aliases in role_aliases.items():
        key_variations = set()
        all_aliases = (*aliases, native_enum)
        for alias in all_aliases:
            key_variations |= EnumField.get_key_variations(alias)
        role_map[native_enum.value] = frozenset(key_variations)
    return role_map


def _xml_credits_to_cb(role_name_persons_map):
    comicbox_credits = {}
    for role_name, persons in role_name_persons_map.items():
        try:
            if not role_name or not persons:
                continue
            for person_name in persons:
                add_credit_role_to_comicbox_credits(
                    person_name, role_name, comicbox_credits
                )
        except Exception:
            logger.exception(f"Parsing credit tag {role_name} {persons}")
    return comicbox_credits


def xml_credits_transform_to_cb(role_tags_enum):
    """Transform xml credit tags to comicbox credits."""
    return MetaSpec(
        key_map={CREDITS_KEY: tuple(r.value for r in role_tags_enum)},
        spec=_xml_credits_to_cb,
    )


def _xml_credits_from_cb(role_aliases: frozenset, comicbox_credits: dict):
    person_names = set()
    for person_name, comicbox_credit in comicbox_credits.items():
        try:
            if not person_name:
                continue
            comicbox_roles = comicbox_credit.get(ROLES_KEY)
            if not comicbox_roles:
                continue
            lower_roles = frozenset({role.lower() for role in comicbox_roles})
            if lower_roles & role_aliases:
                person_names.add(person_name)
        except Exception as exc:
            logger.warning(
                f"Transforming comicbox credit {comicbox_credit} to xml tag: {exc}"
            )
    return person_names


def get_from_cb_func(role_aliases):
    """Create a function that gets person names from comicbox_credits for one xml credit tag."""

    def from_cb(comicbox_credits):
        return _xml_credits_from_cb(role_aliases, comicbox_credits)

    return from_cb


def xml_credits_transform_from_cb(role_tags_enum, role_aliases):
    """Transform comicbox credits into several xml tag credits."""
    role_map = _create_role_enum_to_alias_map(role_aliases)
    metaspecs = []
    for role_tag_enum in role_tags_enum:
        role_tag = role_tag_enum.value
        role_aliases = role_map.get(role_tag)
        func = get_from_cb_func(role_aliases)
        metaspec = MetaSpec(key_map={role_tag: CREDITS_KEY}, spec=func)
        metaspecs.append(metaspec)
    return tuple(metaspecs)
