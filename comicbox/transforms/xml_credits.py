"""XML Credits Mixin."""

from collections.abc import Mapping
from enum import Enum
from logging import getLogger

from glom import Path, glom

from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.transforms.comicbox.credits import add_credit_role_to_comicbox_credits
from comicbox.transforms.credit_role import get_role_enums
from comicbox.transforms.transform_map import DUMMY_PREFIX, KeyTransforms, MultiAssigns

LOG = getLogger(__name__)


def _parse_credit_role(
    source_data, xml_role_enum: Enum, comicbox_credits: dict, format_root_tag: str
):
    role_tag = xml_role_enum.value
    source_path = Path(format_root_tag, role_tag)
    persons = glom(source_data, source_path, default=None)
    if not persons:
        return
    for person_name in persons:
        add_credit_role_to_comicbox_credits(person_name, role_tag, comicbox_credits)


def _xml_credits_to_cb(source_data, _xml_credits, role_tags_enum, format_root_tag):
    comicbox_credits = {}
    for xml_role_enum in role_tags_enum:
        try:
            _parse_credit_role(
                source_data, xml_role_enum, comicbox_credits, format_root_tag
            )
        except Exception:
            LOG.exception(f"Parsing credit tag {xml_role_enum}")
    if not comicbox_credits:
        comicbox_credits = None
    return comicbox_credits


def _unparse_credit_role(
    role_map: Mapping,
    person_name: str,
    comicbox_role_name: str,
    xml_role_tags: dict,
):
    xml_role_enums = get_role_enums(role_map, comicbox_role_name)
    for xml_role_enum in xml_role_enums:
        xml_role_tag = xml_role_enum.value
        persons = xml_role_tags.get(xml_role_tag, set())
        persons.add(person_name)
        xml_role_tags[xml_role_tag] = persons


def _unparse_credit(
    role_map: Mapping, person_name: str, comicbox_credit: dict, xml_role_tags: dict
):
    """Unparse one comicbox credit to an xml tag."""
    if not person_name:
        return
    comicbox_roles = comicbox_credit.get(ROLES_KEY)
    if not comicbox_roles:
        return
    for comicbox_role_name in comicbox_roles:
        _unparse_credit_role(role_map, person_name, comicbox_role_name, xml_role_tags)


def _xml_credits_from_cb(_source_data, comicbox_credits, role_map):
    xml_role_tags = {}
    for person_name, comicbox_credit in comicbox_credits.items():
        try:
            _unparse_credit(role_map, person_name, comicbox_credit, xml_role_tags)
        except Exception as exc:
            LOG.warning(f"Unparse credit {comicbox_credit}: {exc}")
    extra_assigns = tuple(xml_role_tags.items())
    return MultiAssigns(None, extra_assigns)


def xml_credits_transform(role_tags_enum, role_map, format_root_tag):
    """Transform xml credit tags to comicbox credits."""

    def to_cb(source_data, xml_credits):
        return _xml_credits_to_cb(
            source_data, xml_credits, role_tags_enum, format_root_tag
        )

    def from_cb(source_data, comicbox_credits):
        return _xml_credits_from_cb(source_data, comicbox_credits, role_map)

    return KeyTransforms(
        key_map={f"{DUMMY_PREFIX}xml_credits": CREDITS_KEY},
        to_cb=to_cb,
        from_cb=from_cb,
    )
