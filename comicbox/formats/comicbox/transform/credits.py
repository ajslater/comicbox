"""Comicbox credits functions."""

from types import MappingProxyType

from glom import Assign, Path, glom

from comicbox.formats.comicbox.schema import PRIMARY_KEY, ROLES_KEY

ROLE_SPELLING = MappingProxyType({"penciler": "Penciller"})
_PRIMARY = True


def add_credit_role_to_comicbox_credits(
    person_name: str,
    role_name: str,
    comicbox_credits: dict,
) -> None:
    """Add a credit role to the comicbox credits."""
    if not (person_name and role_name):
        return
    role_name = ROLE_SPELLING.get(role_name.lower(), role_name)
    dest_path = Path(person_name, ROLES_KEY, role_name)
    glom(comicbox_credits, Assign(dest_path, {}, missing=dict))


def set_credit_role_primary(
    person_name: str,
    role_name: str,
    comicbox_credits: dict,
) -> None:
    """Mark a person as the primary credit for one of their roles."""
    if not (person_name and role_name):
        return
    role_name = ROLE_SPELLING.get(role_name.lower(), role_name)
    dest_path = Path(person_name, ROLES_KEY, role_name, PRIMARY_KEY)
    glom(comicbox_credits, Assign(dest_path, _PRIMARY, missing=dict))
