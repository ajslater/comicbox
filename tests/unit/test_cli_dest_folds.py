"""
CLI shorthands that fold into another config key.

``-Q``, ``-p``/``-v``, and ``-x`` don't map one-to-one onto a config
key; ``compute_config`` folds them before template validation. These
assert on the resulting settings rather than on any namespace shape, so
they survive a future move of where the folding happens.
"""

from argparse import Namespace

import pytest
from loguru import logger

from comicbox.cli import get_args
from comicbox.config import get_config
from comicbox.config.settings import ComicboxSettings
from comicbox.exceptions import ConfigurationError
from comicbox.print import PrintPhases


def _settings(*flags: str) -> ComicboxSettings:
    return get_config(Namespace(comicbox=get_args(("comicbox", *flags, "x.cbz"))))


# Each count, the level it gives at the shipped default (INFO).
_QUIET_LEVELS = (
    ((), "INFO"),
    (("-Q",), "SUCCESS"),
    (("-QQ",), "WARNING"),
    (("-QQQ",), "ERROR"),
    (("-QQQQ",), "CRITICAL"),
    (("-QQQQQ",), "CRITICAL"),
)


def _level_no(level: str | int) -> int:
    return logger.level(level).no if isinstance(level, str) else level


@pytest.mark.parametrize(("flags", "expected"), _QUIET_LEVELS)
def test_quiet_count_folds_into_loglevel(flags: tuple[str, ...], expected: str) -> None:
    """Each -Q is one step quieter than the default; past the table, CRITICAL."""
    assert _settings(*flags).general.loglevel == expected


@pytest.mark.parametrize("configured", ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"])
def test_each_quiet_is_never_louder(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """Fewer messages with each Q, never more, whatever the config says."""
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", configured)
    levels = [
        _level_no(_settings(*flags).general.loglevel) for flags, _ in _QUIET_LEVELS
    ]
    assert levels[0] == _level_no(configured)
    assert levels == sorted(levels), levels


@pytest.mark.parametrize(
    ("configured", "flags", "expected"),
    [
        ("WARNING", ("-Q",), "WARNING"),
        ("WARNING", ("-QQQ",), "ERROR"),
        ("error", ("-QQ",), "ERROR"),
        ("CRITICAL", ("-Q",), "CRITICAL"),
        ("DEBUG", ("-Q",), "SUCCESS"),
        (40, ("-Q",), 40),
        (10, ("-QQ",), "WARNING"),
    ],
)
def test_quiet_keeps_a_quieter_configured_level(
    monkeypatch: pytest.MonkeyPatch,
    configured: str | int,
    flags: tuple[str, ...],
    expected: str | int,
) -> None:
    """-Q used to replace the level outright, so it made a WARNING config louder."""
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", str(configured))
    assert _settings(*flags).general.loglevel == expected


def test_quiet_does_not_hide_an_unknown_configured_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fold must leave a bad level for validation to report."""
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", "LOUD")
    with pytest.raises(ConfigurationError, match=r"general\.loglevel"):
        _settings("-Q")


def test_print_metadata_shorthand() -> None:
    """-p is shorthand for --print p."""
    assert PrintPhases.METADATA in _settings("-p").print.phases


def test_print_version_shorthand() -> None:
    """-v is shorthand for --print v."""
    assert PrintPhases.VERSION in _settings("-v").print.phases


def test_print_shorthands_add_to_explicit_phases() -> None:
    """The shorthands union with --print rather than replacing it."""
    phases = _settings("--print", "sc", "-p", "-v").print.phases
    assert PrintPhases.METADATA in phases
    assert PrintPhases.VERSION in phases
    assert PrintPhases.SOURCE in phases


def test_no_print_flags_is_empty() -> None:
    """Absent flags leave the phase set empty, not defaulted."""
    assert _settings().print.phases == frozenset()


@pytest.mark.parametrize(
    ("rng", "expected"),
    [
        ("2:4", (2, 4)),
        ("2:", (2, None)),
        (":4", (None, 4)),
        ("2", (2, 2)),
    ],
)
def test_extract_page_range_folds_onto_convert(
    rng: str, expected: tuple[int | None, int | None]
) -> None:
    """-x writes the convert.extract_pages_* pair, not its own dest."""
    settings = _settings("-x", rng)
    actual = (settings.convert.extract_pages_from, settings.convert.extract_pages_to)
    assert actual == expected
