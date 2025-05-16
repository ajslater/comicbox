"""Comic Book Info Credits Transform Mixin."""

from loguru import logger

from comicbox.schemas.comicbookinfo import (
    PERSON_TAG,
    PRIMARY_TAG,
    ROLE_TAG,
)
from comicbox.schemas.comicbox import (
    CREDIT_PRIMARIES_KEY,
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.transforms.comicbox.credits import add_credit_role_to_comicbox_credits
from comicbox.transforms.spec import MetaSpec


def _get_cbi_credit_parts(cbi_credit):
    cbi_person = cbi_credit.get(PERSON_TAG, "")
    cbi_role = cbi_credit.get(ROLE_TAG, "")
    return cbi_person, cbi_role


def _cbi_credits_to_cb(cbi_credits):
    comicbox_credits = {}
    for cbi_credit in cbi_credits:
        try:
            cbi_person, cbi_role = _get_cbi_credit_parts(cbi_credit)
            add_credit_role_to_comicbox_credits(cbi_person, cbi_role, comicbox_credits)
        except Exception as exc:
            logger.warning(f"Parsing credit {cbi_credit}: {exc}")
    return comicbox_credits


def cbi_credits_transform_to_cb(credits_tag):
    """Transform for CBI credits."""
    return MetaSpec(
        key_map={CREDITS_KEY: credits_tag},
        spec=_cbi_credits_to_cb,
    )


def _cbi_credits_primary_to_cb(cbi_credits):
    credit_primaries = {}
    for cbi_credit in cbi_credits:
        if cbi_credit.get(PRIMARY_TAG):
            cbi_person, cbi_role = _get_cbi_credit_parts(cbi_credit)
            credit_primaries[cbi_role] = cbi_person
    return credit_primaries


def cbi_credits_primary_to_cb(credits_tag):
    """Transform the credit primaries key from cbi credits."""
    return MetaSpec(
        key_map={CREDIT_PRIMARIES_KEY: credits_tag}, spec=_cbi_credits_primary_to_cb
    )


def _cbi_credit_from_cb(person_name, comicbox_credit, cbi_credits, credit_primaries):
    """Unparse one comicbox credit into cbi credits."""
    if not person_name:
        return
    comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
    for role_name in comicbox_roles:
        cbi_credit = {PERSON_TAG: person_name, ROLE_TAG: role_name}
        if credit_primaries and credit_primaries.get(role_name) == person_name:
            cbi_credit[PRIMARY_TAG] = True
        cbi_credits.append(cbi_credit)


def _cbi_credits_from_cb(values):
    comicbox_credits = values.get(CREDITS_KEY)
    credit_primaries = values.get(CREDIT_PRIMARIES_KEY)
    cbi_credits = []
    for person_name, comicbox_credit in comicbox_credits.items():
        try:
            _cbi_credit_from_cb(
                person_name, comicbox_credit, cbi_credits, credit_primaries
            )
        except Exception as exc:
            logger.warning(f"Unparsing credit {comicbox_credit} - {exc}")
            logger.exception("debug")
    return cbi_credits


def cbi_credits_transform_from_cb(credits_tag):
    """Transform for CBI credits."""
    return MetaSpec(
        key_map={credits_tag: (CREDITS_KEY, CREDIT_PRIMARIES_KEY)},
        spec=_cbi_credits_from_cb,
    )
