"""Comic Book Info Credits Transform Mixin."""

from logging import getLogger

from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    PERSON_TAG,
    PRIMARY_TAG,
    ROLE_TAG,
)
from comicbox.schemas.comicbox_mixin import (
    CREDIT_PRIMARIES_KEY,
    ROLES_KEY,
)
from comicbox.transforms.base import add_credit_role_to_comicbox_credits
from comicbox.transforms.transform_map import KeyTransforms, MultiAssigns

LOG = getLogger(__name__)


def _parse_credit(cbi_credit: dict, comicbox_credits: dict, credit_primaries: dict):
    """Parse one CBI credit into a comicbox credit."""
    cbi_person = cbi_credit.get(PERSON_TAG, "")
    cbi_role = cbi_credit.get(ROLE_TAG, "")
    primary = cbi_credit.get(PRIMARY_TAG)
    add_credit_role_to_comicbox_credits(cbi_person, cbi_role, comicbox_credits)
    if primary:
        credit_primaries[cbi_role] = cbi_person


def _cbi_credits_to_cb(_source_data, cbi_credits):
    comicbox_credits = {}
    credit_primaries = {}
    for cbi_credit in cbi_credits:
        try:
            _parse_credit(cbi_credit, comicbox_credits, credit_primaries)
        except Exception as exc:
            LOG.warning(f"Parsing credit {cbi_credit}: {exc}")
    if credit_primaries:
        result = MultiAssigns(
            comicbox_credits, ((CREDIT_PRIMARIES_KEY, credit_primaries),)
        )
    else:
        result = comicbox_credits
    return result


def _unparse_credit(source_data, person_name, comicbox_credit, cbi_credits):
    """Unparse one comicbox credit into cbi credits."""
    if not person_name:
        return
    comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
    for role_name in comicbox_roles:
        cbi_credit = {PERSON_TAG: person_name, ROLE_TAG: role_name}
        if source_data.get(CREDIT_PRIMARIES_KEY, {}).get(role_name) == person_name:
            cbi_credit[PRIMARY_TAG] = True
        cbi_credits.append(cbi_credit)


def _cbi_credits_from_cb(source_data, comicbox_credits):
    cbi_credits = []
    for person_name, comicbox_credit in comicbox_credits.items():
        try:
            _unparse_credit(source_data, person_name, comicbox_credit, cbi_credits)
        except Exception as exc:
            LOG.warning(f"Unparsing credit {comicbox_credit} - {exc}")
    return cbi_credits


def cbi_credits_transform(credits_tag):
    """Transform for CBI credits."""
    return KeyTransforms(
        key_map={credits_tag: CREDITS_TAG},
        to_cb=_cbi_credits_to_cb,
        from_cb=_cbi_credits_from_cb,
    )
