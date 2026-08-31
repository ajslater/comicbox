"""Comicbox canonicalizes credit roles to the MetronInfo vocabulary."""

import pytest

from comicbox.enums.metroninfo import MetronRoleEnum
from comicbox.formats.base.fields.comicbox import RoleField
from comicbox.formats.base.fields.enum_fields import EnumField
from comicbox.formats.comic_book_info.transform.credits import cbi_role_from_cb
from comicbox.formats.metron_info.transform.credits import (
    ROLE_ALIASES,
    _create_role_variations_to_enum_map,
    _resolve_role_enums,
)

_ROLE_FIELD = RoleField()
_METRON_ROLE_MAP = _create_role_variations_to_enum_map(ROLE_ALIASES)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Spellings that used to survive as separate roles after a merge.
        ("Cover Artist", "Cover"),
        ("CoverArtist", "Cover"),
        ("colorDesigner", "Cover"),
        ("covers", "Cover"),
        ("Colourist", "Colorist"),
        ("Colorer", "Colorist"),
        ("colorist", "Colorist"),
        ("penciler", "Penciller"),
        # Foreign vocabularies fold into their Metron equivalent.
        ("Author", "Writer"),
        ("writer", "Writer"),
        ("inks", "Inker"),
        ("pencils", "Penciller"),
        # An alias naming a role Metron actually has keeps that distinction
        # instead of collapsing into the coarser role it is filed under.
        ("breakdowns", "Breakdowns"),
        ("finishes", "Finishes"),
        ("plotter", "Plot"),
        ("scripter", "Script"),
        # Comicbox extras Metron has no role for.
        ("creator", "Creator"),
        ("painting", "Painter"),
    ],
)
def test_role_canonicalizes(value: str, expected: str) -> None:
    """Every known spelling deserializes to one canonical role name."""
    assert _ROLE_FIELD.deserialize(value) == expected


def test_role_snake_case_matches() -> None:
    """Lookup generates the same key variations the map was built with."""
    assert _ROLE_FIELD.deserialize("editor_in_chief") == "Editor In Chief"


def test_unknown_role_passes_through() -> None:
    """An unrecognized role stays readable instead of becoming Other."""
    assert _ROLE_FIELD.deserialize("Assistant Gopher") == "Assistant Gopher"


def test_every_metron_role_is_canonical() -> None:
    """Metron's own vocabulary is the fixed point of canonicalization."""
    for enum in MetronRoleEnum:
        assert _ROLE_FIELD.deserialize(enum.value) == enum.value


@pytest.mark.parametrize(
    ("role_name", "expected"),
    [
        # Painter is the one role that legitimately expands: one person doing
        # pencils, inks and colors.
        ("Painter", ["Penciller", "Inker", "Colorist"]),
        # These share an alias with a coarser role but name a real Metron
        # role, so they must not write both.
        ("Breakdowns", ["Breakdowns"]),
        ("Finishes", ["Finishes"]),
        ("Script", ["Script"]),
        ("Penciller", ["Penciller"]),
    ],
)
def test_metron_write_fan_out(role_name: str, expected: list[str]) -> None:
    """Only Painter writes more Metron roles than it started with."""
    role_enums = _METRON_ROLE_MAP[role_name.lower()]
    resolved = [enum.value for enum in _resolve_role_enums(role_name, role_enums)]
    assert resolved == expected


@pytest.mark.parametrize(
    ("role_name", "expected"),
    [
        ("Colorist", "Colorer"),
        ("Gray Tone", "Colorer"),
        ("Cover", "Cover Artist"),
        ("Editor In Chief", "Editor"),
        ("Embellisher", "Inker"),
        ("Script", "Writer"),
        ("Writer", "Writer"),
        # No ComicBookInfo equivalent: written verbatim, which its
        # "common but not restricted to" vocabulary allows.
        ("Painter", "Painter"),
        ("Logo Design", "Logo Design"),
    ],
)
def test_cbi_role_projection(role_name: str, expected: str) -> None:
    """Writing ComicBookInfo projects onto its own smaller vocabulary."""
    assert cbi_role_from_cb(role_name) == expected


def test_ordered_key_variations_are_deterministic() -> None:
    """The literal spelling is tried before any collapsed variation."""
    variations = EnumField.get_ordered_key_variations("Cover Artist")
    assert variations[0] == "cover artist"
    assert "coverartist" in variations
