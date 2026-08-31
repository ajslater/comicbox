"""
End-to-end tests for ``-c/--config``: an alternate config file must bite.

Regression: ``-c`` parses to the ``general_config`` argparse dest, which
``post_process_args`` folds into ``args.comicbox.general.config``.
``read_config_sources`` read ``args.comicbox.config`` — one level too
shallow — inside a blanket ``contextlib.suppress(AttributeError,
KeyError)``. The lookup raised, the suppress swallowed it, and every
``-c`` run silently used the built-in defaults. Nothing warned, and no
test compared behavior with and without the flag.

These tests assert on *resulting settings*, not on the key path, so they
stay honest if the args reshaping moves again.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

import pytest
from confuse import ConfigReadError

from comicbox.cli import get_args
from comicbox.config import get_config

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

# Values deliberately unlike the config_default.yaml defaults
# (recurse False, dest_path ".", jobs 1, auto_threshold 0.95).
_ALT_CONFIG = """
comicbox:
  general:
    recurse: True
    dest_path: /tmp/comicbox-alt-dest
    jobs: 4
  online:
    tuning:
      auto_threshold: 0.42
"""


@pytest.fixture
def alt_config(tmp_path: Path) -> Path:
    """Write an alternate config file that differs from every default."""
    path = tmp_path / "alt.yaml"
    path.write_text(_ALT_CONFIG)
    return path


def _assert_is_default(args: Namespace | Mapping) -> None:
    settings = get_config(args)
    assert settings.general.recurse is False
    assert str(settings.general.dest_path) == "."
    assert settings.general.jobs == 1
    assert settings.online.tuning.auto_threshold == 0.95


def _assert_is_alternate(args: Namespace | Mapping) -> None:
    settings = get_config(args)
    assert settings.general.recurse is True
    assert str(settings.general.dest_path) == "/tmp/comicbox-alt-dest"
    assert settings.general.jobs == 4
    assert settings.online.tuning.auto_threshold == 0.42


def test_baseline_without_config_flag() -> None:
    """Without ``-c`` the bundled defaults win. Pins the contrast case."""
    _assert_is_default(Namespace(comicbox=get_args(("comicbox", "x.cbz"))))


def test_cli_config_file_changes_behavior(alt_config: Path) -> None:
    """``-c FILE`` through the real CLI parser must change the settings."""
    cns = get_args(("comicbox", "-c", str(alt_config), "x.cbz"))
    _assert_is_alternate(Namespace(comicbox=cns))


def test_long_config_flag_changes_behavior(alt_config: Path) -> None:
    """``--config FILE`` is the same path as ``-c``."""
    cns = get_args(("comicbox", "--config", str(alt_config), "x.cbz"))
    _assert_is_alternate(Namespace(comicbox=cns))


def test_mapping_config_file_changes_behavior(alt_config: Path) -> None:
    """The Mapping args shape honors the same nested key."""
    _assert_is_alternate({"comicbox": {"general": {"config": str(alt_config)}}})


def test_cli_args_still_beat_the_config_file(alt_config: Path) -> None:
    """
    Layering order survives the fix: CLI args sit above the ``-c`` file.

    ``read_config_sources`` adds the ``-c`` file before ``set_args``, so
    an explicit flag must still win over the same key in the file.
    """
    cns = get_args(("comicbox", "-c", str(alt_config), "-j", "7", "x.cbz"))
    settings = get_config(Namespace(comicbox=cns))
    assert settings.general.jobs == 7  # CLI beats the file
    assert settings.general.recurse is True  # file still supplies the rest


def test_missing_config_file_errors(tmp_path: Path) -> None:
    """A ``-c`` path that doesn't exist must fail loudly, not fall back."""
    missing = tmp_path / "nope.yaml"
    cns = get_args(("comicbox", "-c", str(missing), "x.cbz"))
    with pytest.raises(ConfigReadError):
        get_config(Namespace(comicbox=cns))
