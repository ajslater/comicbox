"""
Every CLI dest must name a real config template path.

The ``-c`` bug happened because the flat argparse dest and the config
key it fed were two separately maintained strings, and a reshaper moved
one without the other. Dotted dests make them the same string; this test
is what keeps them that way, by walking every parser action against the
confuse template instead of trusting a hand-kept list.
"""

from argparse import SUPPRESS
from typing import Any

import pytest
from confuse import MappingTemplate, Template

from comicbox.cli.parser import ONLINE_RUNTIME_DESTS, build_parser
from comicbox.config import _TEMPLATE
from comicbox.version import PACKAGE_NAME

# Dests folded into another key by ``compute_config`` rather than
# landing on one of their own. Each is a CLI shorthand:
# -Q -> general.loglevel, -p/-v -> print.phases.
_FOLDED = frozenset({"general.quiet", "print.metadata", "print.version"})


def _config_tree_actions() -> list[Any]:
    """Every parser action that is supposed to name a template path."""
    return [
        action
        for action in build_parser()._actions
        if action.dest not in ONLINE_RUNTIME_DESTS and action.dest != SUPPRESS
    ]


def _resolve(dotted: str) -> None:
    """Walk a dotted dest through the template, raising if it dead-ends."""
    template: Template[Any] = _TEMPLATE
    for segment in (PACKAGE_NAME, *dotted.split(".")):
        if not isinstance(template, MappingTemplate):
            reason = f"{dotted}: {segment} has no subkeys in the template"
            raise TypeError(reason)
        subtemplates: dict[str, Template[Any]] = template.subtemplates
        if segment not in subtemplates:
            reason = f"{dotted}: no such key in the config template"
            raise KeyError(reason)
        template = subtemplates[segment]


@pytest.mark.parametrize("action", _config_tree_actions(), ids=lambda a: a.dest)
def test_dest_resolves_in_the_config_template(action: Any) -> None:
    """A config-tree dest is the template path it sets, dots and all."""
    if action.dest in _FOLDED:
        # Folded dests are deliberately absent from the template;
        # compute_config consumes them before validation.
        return
    assert "." in action.dest, f"{action.dest} must name its template path"
    _resolve(action.dest)


@pytest.mark.parametrize("action", _config_tree_actions(), ids=lambda a: a.dest)
def test_value_taking_actions_declare_a_metavar(action: Any) -> None:
    """
    Without an explicit metavar argparse renders ``GENERAL.DEST_PATH``.

    Dotted dests make the derived metavar user-visible, so every option
    that takes a value has to name its own.
    """
    if action.nargs == 0 or not action.option_strings:
        return
    assert action.metavar, f"{action.dest} needs an explicit metavar"


def test_folded_dests_are_absent_from_the_template() -> None:
    """
    The fold list can't rot into a typo that silently drops a flag.

    If one of these ever gains a template key, the fold in
    compute_config is redundant and this test says so.
    """
    for dotted in _FOLDED:
        with pytest.raises((KeyError, TypeError)):
            _resolve(dotted)
