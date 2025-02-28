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

    def parse_credits(self, data):
        """Aggregate credits from individual role tags to contributors entries."""
        comicbox_credits = {}
        for xml_role_tag_enum in self.ROLE_TAGS_ENUM:
            try:
                role_name = xml_role_tag_enum.value
                persons = data.pop(role_name, None)
                if not persons:
                    continue
                for person_name in persons:
                    self.add_credit_role_to_comicbox_credits(
                        person_name, role_name, comicbox_credits
                    )
            except Exception:
                LOG.exception(f"{self._path} parsing credit tag {xml_role_tag_enum}")

        if comicbox_credits:
            data[CREDITS_KEY] = comicbox_credits

        return data

    def _unparse_credit_role(self, person_name, comicbox_role_name, xml_role_tags):
        if xml_role_tag_tuple := self.ROLE_MAP.get(comicbox_role_name.lower()):
            for xml_role_tag in xml_role_tag_tuple:
                persons = xml_role_tags.get(xml_role_tag, set())
                persons.add(person_name)
                xml_role_tags[xml_role_tag] = persons

    def _unparse_credit(self, person_name, comicbox_credit, xml_role_tags):
        """Unparse one comicbox credit to an xml tag."""
        if not person_name:
            return
        comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
        for comicbox_role_name in comicbox_roles:
            self._unparse_credit_role(person_name, comicbox_role_name, xml_role_tags)

    def unparse_credits(self, data):
        """Disaggregate credits from comicbox credits to individual role tags."""
        comicbox_credits = data.pop(CREDITS_KEY, {})
        xml_role_tags = {}
        for person_name, comicbox_credit in comicbox_credits.items():
            try:
                self._unparse_credit(person_name, comicbox_credit, xml_role_tags)
            except Exception as exc:
                LOG.warning(f"{self._path} unparse credit {comicbox_credit}: {exc}")

        for xml_tag, persons in xml_role_tags.items():
            data[xml_tag] = persons

        return data
