"""
Every enum-backed CLI flag's ``choices`` must be its enum's values.

``--merge-mode`` always built its choices from ``MergeMode``; the four
online flags spelled theirs out as literal tuples instead, so what
argparse accepted and what the value parsed into were two separately
maintained lists. Nothing caught a divergence: the dest/template test
pins a flag to its config key and the defaults test pins the YAML to the
dataclass, but neither looks at the accepted values. Adding a level to
``Effort`` or renaming a ``MatchMode`` would have left the flag
rejecting a value its own parser understands.

The flags now derive ``choices`` from the enums. This test keeps them
derived, keeps the help text listing every value, and fails on any *new*
choices-taking flag until it is either mapped to its enum here or listed
as deliberately not enum-backed — so neither map below can rot into a
permanent excuse.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from comicbox.cli.parser import build_parser
from comicbox.config.online.settings import CacheMode, Effort, MatchMode, Prompts
from comicbox.config.settings import MergeMode

if TYPE_CHECKING:
    from argparse import Action, ArgumentParser
    from enum import Enum

# Flag -> the enum whose values it accepts.
_ENUM_BACKED: dict[str, type[Enum]] = {
    "--merge-mode": MergeMode,
    "--match": MatchMode,
    "--prompts": Prompts,
    "--cache": CacheMode,
    "--effort": Effort,
}

# Choices that legitimately come from somewhere other than a comicbox
# enum: --pdf-pages takes its values from the installed pdffile.
_NOT_ENUM_BACKED = frozenset({"--pdf-pages"})

_PARSER: ArgumentParser = build_parser()


def _choices_actions() -> list[Action]:
    """Every parser action that constrains its value to a fixed set."""
    return [action for action in _PARSER._actions if action.choices is not None]


def _action_for(flag: str) -> Action:
    for action in _choices_actions():
        if flag in action.option_strings:
            return action
    reason = f"{flag} is not a choices-taking parser option"
    raise AssertionError(reason)


@pytest.mark.parametrize(("flag", "enum_class"), _ENUM_BACKED.items())
def test_choices_are_the_enum_values(flag: str, enum_class: type[Enum]) -> None:
    """A flag accepts exactly its enum's values, in the enum's order."""
    assert tuple(_action_for(flag).choices or ()) == tuple(
        member.value for member in enum_class
    )


@pytest.mark.parametrize(("flag", "enum_class"), _ENUM_BACKED.items())
def test_help_lists_every_choice(flag: str, enum_class: type[Enum]) -> None:
    """
    The help text names every value the flag accepts.

    Deriving ``choices`` stops argparse from rejecting a new enum
    member, but the help string is still hand-written prose; without
    this, a new member is accepted and undocumented.
    """
    help_text = _action_for(flag).help or ""
    missing = [
        member.value
        for member in enum_class
        if not re.search(rf"\b{re.escape(str(member.value))}\b", help_text)
    ]
    assert not missing, f"{flag} help does not mention {missing}"


def test_every_choices_flag_declares_where_its_values_come_from() -> None:
    """A new choices-taking flag must be mapped to an enum or exempted."""
    accounted = set(_ENUM_BACKED) | _NOT_ENUM_BACKED
    unaccounted = [
        action.option_strings
        for action in _choices_actions()
        if not accounted.intersection(action.option_strings)
    ]
    assert not unaccounted, (
        f"{unaccounted} take choices but name no source for them; "
        "map the flag to its enum or add it to _NOT_ENUM_BACKED."
    )


def test_the_exemption_list_is_not_stale() -> None:
    """An exempted flag that gained an enum (or vanished) must be re-filed."""
    for flag in _NOT_ENUM_BACKED:
        assert _action_for(flag).choices, f"{flag} no longer takes choices"
