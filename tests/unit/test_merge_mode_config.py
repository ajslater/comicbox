"""
The ``write.merge_mode`` surface: config file and CLI flag.

The mode was reachable only through the Python write API for two
releases. The confuse template and ``_build_write_settings`` never read
it, so a value in a config file was silently ignored, and the sole
user-facing knob was the deprecated ``--replace`` bool — which selected
``update``, not ``replace``, and left ``replace`` unreachable outside
Python entirely.

These pin the three entry points against resulting settings rather than
key paths, so they stay honest if the args reshaping moves.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

import pytest

from comicbox.cli import get_args
from comicbox.config import get_config
from comicbox.config.settings import MergeMode

if TYPE_CHECKING:
    from pathlib import Path

_ALT_CONFIG = """
comicbox:
  write:
    merge_mode: update
"""


@pytest.fixture
def alt_config(tmp_path: Path) -> Path:
    """Write a config file selecting a non-default merge mode."""
    path = tmp_path / "merge-mode.yaml"
    path.write_text(_ALT_CONFIG)
    return path


def test_default_merge_mode_is_additive() -> None:
    """The contrast case: nothing supplied means additive."""
    assert get_config().write.merge_mode is MergeMode.ADDITIVE


def test_config_file_merge_mode_is_honored(alt_config: Path) -> None:
    """A ``-c`` file's merge_mode reaches the settings dataclass."""
    cns = get_args(("comicbox", "-c", str(alt_config), "x.cbz"))
    settings = get_config(Namespace(comicbox=cns))
    assert settings.write.merge_mode is MergeMode.UPDATE


def test_mapping_config_merge_mode_is_honored() -> None:
    """The Mapping args shape honors the same key."""
    settings = get_config({"comicbox": {"write": {"merge_mode": "replace"}}})
    assert settings.write.merge_mode is MergeMode.REPLACE


def test_cli_merge_mode_beats_the_config_file(alt_config: Path) -> None:
    """An explicit ``--merge-mode`` sits above the ``-c`` file."""
    cns = get_args(
        ("comicbox", "-c", str(alt_config), "--merge-mode", "replace", "x.cbz")
    )
    settings = get_config(Namespace(comicbox=cns))
    assert settings.write.merge_mode is MergeMode.REPLACE


def test_cli_merge_mode_lands_on_the_write_block() -> None:
    """``--merge-mode`` reaches the write block of the built settings."""
    cns = get_args(("comicbox", "--merge-mode", "update", "x.cbz"))
    settings = get_config(Namespace(comicbox=cns))
    assert settings.write.merge_mode is MergeMode.UPDATE


def test_cli_merge_mode_rejects_unknown_choice() -> None:
    """Argparse guards the CLI surface before confuse ever sees it."""
    with pytest.raises(SystemExit):
        get_args(("comicbox", "--merge-mode", "bogus", "x.cbz"))


def test_replace_flag_is_gone() -> None:
    """``--replace`` was removed; it must not silently parse again."""
    with pytest.raises(SystemExit):
        get_args(("comicbox", "--replace", "x.cbz"))


def test_bad_config_merge_mode_raises_naming_the_valid_values() -> None:
    """
    An unparseable config value fails loudly instead of defaulting.

    Silently ignoring a bad config value is the defect class the config
    audit removed elsewhere; the message names the key and the choices.
    """
    with pytest.raises(ValueError, match=r"write\.merge_mode") as exc_info:
        get_config({"comicbox": {"write": {"merge_mode": "bogus"}}})
    message = str(exc_info.value)
    for mode in MergeMode:
        assert mode.value in message
