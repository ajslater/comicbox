"""The primary credit flag belongs to a (person, role) pair."""

from typing import Any

from comicbox.formats.comic_book_info.transform import ComicBookInfoTransform

_TRANSFORM = ComicBookInfoTransform(None)
# The transform works on the post-load root key, not the "ComicBookInfo/1.0"
# data key the JSON document uses.
_ROOT_TAG = "ComicBookInfo"


def _to_cb(cbi_credits: list[dict[str, Any]]) -> dict:
    native = {_ROOT_TAG: {"credits": cbi_credits}}
    return dict(_TRANSFORM.to_comicbox(native)["comicbox"]["credits"])


def _from_cb(comicbox_credits: dict[str, Any]) -> list[dict[str, Any]]:
    native = _TRANSFORM.from_comicbox({"comicbox": {"credits": comicbox_credits}})
    return native[_ROOT_TAG]["credits"]


def test_primary_lands_on_the_role() -> None:
    """A primary ComicBookInfo credit marks that person's role."""
    credits_md = _to_cb(
        [
            {"person": "Alan Moore", "role": "Writer", "primary": True},
            {"person": "Dave Gibbons", "role": "Artist"},
        ]
    )
    assert credits_md["Alan Moore"]["roles"]["Writer"]["primary"] is True
    assert not credits_md["Dave Gibbons"]["roles"]["Artist"].get("primary")


def test_primary_does_not_leak_across_a_persons_roles() -> None:
    """
    Being the primary Writer does not make you the primary Inker.

    The old flat credit_primaries map was keyed by role alone, so a person
    who was primary for one role matched every other role they held.
    """
    credits_md = _to_cb(
        [
            {"person": "Alan Moore", "role": "Writer", "primary": True},
            {"person": "Alan Moore", "role": "Inker"},
        ]
    )
    roles = credits_md["Alan Moore"]["roles"]
    assert roles["Writer"]["primary"] is True
    assert not roles["Inker"].get("primary")


def test_two_people_can_be_primary_for_different_roles() -> None:
    """Each role has its own primary credit."""
    credits_md = _to_cb(
        [
            {"person": "Joe Orlando", "role": "Writer", "primary": True},
            {"person": "Wally Wood", "role": "Penciller", "primary": True},
        ]
    )
    assert credits_md["Joe Orlando"]["roles"]["Writer"]["primary"] is True
    assert credits_md["Wally Wood"]["roles"]["Penciller"]["primary"] is True


def test_primary_round_trips() -> None:
    """The flag survives a read and a write."""
    cbi_credits = [
        {"person": "Alan Moore", "role": "Writer", "primary": True},
        {"person": "Alan Moore", "role": "Inker"},
    ]
    written = _from_cb(_to_cb(cbi_credits))
    by_role = {credit["role"]: credit for credit in written}
    assert by_role["Writer"].get("primary") is True
    assert "primary" not in by_role["Inker"]
