"""
CLI shorthands that fold into another config key.

``-Q``, ``-p``/``-v``, and ``-x`` don't map one-to-one onto a config
key; ``compute_config`` folds them before template validation. These
assert on the resulting settings rather than on any namespace shape, so
they survive a future move of where the folding happens.
"""

from argparse import Namespace

import pytest

from comicbox.cli import get_args
from comicbox.config import get_config
from comicbox.config.settings import ComicboxSettings
from comicbox.print import PrintPhases


def _settings(*flags: str) -> ComicboxSettings:
    return get_config(Namespace(comicbox=get_args(("comicbox", *flags, "x.cbz"))))


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((), "INFO"),
        (("-Q",), "INFO"),
        (("-QQ",), "SUCCESS"),
        (("-QQQ",), "WARNING"),
        (("-QQQQ",), "ERROR"),
        (("-QQQQQ",), "CRITICAL"),
        (("-QQQQQQ",), "CRITICAL"),
    ],
)
def test_quiet_count_folds_into_loglevel(flags: tuple[str, ...], expected: str) -> None:
    """Each -Q ratchets the loglevel; past the table it pins at CRITICAL."""
    assert _settings(*flags).general.loglevel == expected


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
