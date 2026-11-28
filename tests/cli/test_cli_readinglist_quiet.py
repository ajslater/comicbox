"""
``comicbox rl -Q`` logs as ``comicbox -Q`` does.

The same table (each Q one step quieter than INFO) and the same rule:
never louder than the configured ``general.loglevel``, which rl honors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from comicbox import logger as comicbox_logger
from tests.util.readinglist_cli import CRIMSON_TIDE, cli_run, rl_main

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


@pytest.fixture
def levels(monkeypatch: pytest.MonkeyPatch) -> list[str | int]:
    """Record the level each rl command sets up logging at."""
    seen: list[str | int] = []

    def init_logging(
        loglevel: str | int = "INFO", *_args: object, **_kw: object
    ) -> None:
        seen.append(loglevel)

    monkeypatch.setattr(comicbox_logger, "init_logging", init_logging)
    return seen


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((), "INFO"),
        (("-Q",), "SUCCESS"),
        (("-QQ",), "WARNING"),
        (("-QQQ",), "ERROR"),
        (("-QQQQ",), "CRITICAL"),
        (("-QQQQQ",), "CRITICAL"),
    ],
)
def test_rl_quiet_uses_the_comicbox_table(
    levels: list[str | int], flags: tuple[str, ...], expected: str
) -> None:
    assert rl_main(*flags, "print", str(CRIMSON_TIDE)) == 0
    assert levels == [expected]


@pytest.mark.parametrize(
    ("configured", "flags", "expected"),
    [
        ("WARNING", (), "WARNING"),
        ("debug", (), "DEBUG"),
        ("WARNING", ("-Q",), "WARNING"),
        ("CRITICAL", ("-Q",), "CRITICAL"),
        ("ERROR", ("-QQ",), "ERROR"),
        ("DEBUG", ("-Q",), "SUCCESS"),
    ],
)
def test_rl_honors_the_configured_level_and_is_never_louder(
    monkeypatch: pytest.MonkeyPatch,
    levels: list[str | int],
    configured: str,
    flags: tuple[str, ...],
    expected: str,
) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", configured)
    assert rl_main(*flags, "print", str(CRIMSON_TIDE)) == 0
    assert levels == [expected]


def test_rl_reports_a_bad_configured_level(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", "LOUD")
    code, _, err = cli_run(capsys, "rl", "-Q", "print", str(CRIMSON_TIDE))
    assert code == 1
    assert "general.loglevel: unknown level 'LOUD'" in err
    assert "Traceback" not in err


def test_reading_the_level_prints_no_config_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A command that uses no other setting is not the place for its warnings."""
    (tmp_path / "config.yaml").write_text("comicbox:\n  write:\n    formats: [cxi]\n")
    code, _, err = cli_run(capsys, "rl", "print", str(CRIMSON_TIDE))
    assert code == 0
    assert "cxi" not in err
