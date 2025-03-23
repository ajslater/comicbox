"""Comicbox credits functions."""

from types import MappingProxyType

from glom import Assign, glom
from icecream import ic

from comicbox.schemas.comicbox_mixin import ROLES_KEY

ROLE_SPELLING = MappingProxyType({"penciler": "Penciller"})


def add_credit_role_to_comicbox_credits(
    person_name: str,
    role_name: str,
    comicbox_credits: dict,
):
    """Add a credit role to the comicbox credits."""
    if not (person_name and role_name):
        return
    role_name = ROLE_SPELLING.get(role_name.lower(), role_name)
    glom(
        comicbox_credits,
        Assign(f"{person_name}.{ROLES_KEY}.{role_name}", {}, missing=dict),
    )
    ic(comicbox_credits)
