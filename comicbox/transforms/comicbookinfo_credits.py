"""Comic Book Info Credits Transform Mixin."""

from logging import getLogger
from types import MappingProxyType

from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    PERSON_TAG,
    ROLE_TAG,
)
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.transforms.json_transforms import JsonTransform

LOG = getLogger(__name__)


class ComicBookInfoCreditsTransformMixin(JsonTransform):
    """Comic Book Info Credits Transform Mixin."""

    # comicbookinfo and comictagger use the same tag names
    CREDITS_TAG = CREDITS_TAG
    ROLE_TAG = ROLE_TAG
    PERSON_TAG = PERSON_TAG
    ROLE_MISPELLING_MAP = MappingProxyType({"penciler": "Penciller"})

    def _parse_credit(self, cbi_credit: dict, comicbox_credits: dict):
        """Parse one CBI credit into a comicbox credit."""
        cbi_person = cbi_credit.get(self.PERSON_TAG, "")
        cbi_role = cbi_credit.get(self.ROLE_TAG, "")
        self.add_credit_role_to_comicbox_credits(cbi_person, cbi_role, comicbox_credits)

    def parse_credits(self, data):
        """Aggregate dict from comicbookinfo style list."""
        cbi_credits = data.pop(self.CREDITS_TAG, None)
        if not cbi_credits:
            return data
        comicbox_credits = {}
        for cbi_credit in cbi_credits:
            try:
                self._parse_credit(cbi_credit, comicbox_credits)
            except Exception as exc:
                LOG.warning(f"{self._path}: Parsing credit {cbi_credit}: {exc}")

        if comicbox_credits:
            data[CREDITS_KEY] = comicbox_credits
        return data

    def _unparse_credit(self, person_name, comicbox_credit, cbi_credits):
        """Unparse one comicbox credit into cbi credits."""
        if not person_name:
            return
        comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
        for role_name in comicbox_roles:
            cbi_credit = {PERSON_TAG: person_name, ROLE_TAG: role_name}
            cbi_credits.append(cbi_credit)

    def unparse_credits(self, data):
        """Create comicbookinfo style list from comicbox credits."""
        comicbox_credits = data.pop(CREDITS_KEY, None)
        if not comicbox_credits:
            return data
        cbi_credits = []
        for person_name, comicbox_credit in comicbox_credits.items():
            try:
                self._unparse_credit(person_name, comicbox_credit, cbi_credits)
            except Exception as exc:
                LOG.warning(f"{self._path}: Unparsing credit {comicbox_credit} - {exc}")
        if cbi_credits:
            data[self.CREDITS_TAG] = cbi_credits
        return data
