"""XML Credits Mixin."""

from enum import Enum
from logging import getLogger

from stringcase import capitalcase

from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.transforms.credit_role_tag import CreditRoleTagTransformMixin

LOG = getLogger(__name__)


class XmlCreditsTransformMixin(CreditRoleTagTransformMixin):
    """XML Credits Mixin."""

    ROLE_TAGS_ENUM = Enum

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return capitalcase(data)

    @classmethod
    def _parse_credit_role(cls, data, xml_role_enum: Enum, comicbox_credits: dict):
        role_tag = xml_role_enum.value
        persons = data.pop(role_tag, ())
        for person_name in persons:
            cls.add_credit_role_to_comicbox_credits(
                person_name, role_tag, comicbox_credits
            )

    def parse_credits(self, data):
        """Aggregate credits from individual role tags to contributors entries."""
        comicbox_credits = {}
        for xml_role_enum in self.ROLE_TAGS_ENUM:
            try:
                self._parse_credit_role(data, xml_role_enum, comicbox_credits)
            except Exception:
                LOG.exception(f"{self._path} parsing credit tag {xml_role_enum}")

        if comicbox_credits:
            data[CREDITS_KEY] = comicbox_credits

        return data

    @classmethod
    def _unparse_credit_role(
        cls, person_name: str, comicbox_role_name: str, xml_role_tags: dict
    ):
        xml_role_enums = cls.get_role_enums(comicbox_role_name)
        for xml_role_enum in xml_role_enums:
            xml_role_tag = xml_role_enum.value
            persons = xml_role_tags.get(xml_role_tag, set())
            persons.add(person_name)
            xml_role_tags[xml_role_tag] = persons

    @classmethod
    def _unparse_credit(
        cls, person_name: str, comicbox_credit: dict, xml_role_tags: dict
    ):
        """Unparse one comicbox credit to an xml tag."""
        if not person_name:
            return
        comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
        for comicbox_role_name in comicbox_roles:
            cls._unparse_credit_role(person_name, comicbox_role_name, xml_role_tags)

    def unparse_credits(self, data):
        """Disaggregate credits from comicbox credits to individual role tags."""
        comicbox_credits = data.pop(CREDITS_KEY, {})
        xml_role_tags = {}
        for person_name, comicbox_credit in comicbox_credits.items():
            try:
                self._unparse_credit(person_name, comicbox_credit, xml_role_tags)
            except Exception as exc:
                LOG.warning(f"{self._path} unparse credit {comicbox_credit}: {exc}")

        data.update(xml_role_tags)
        return data
