"""
Bad config is reported as what it is, and never drops the rest.

A malformed user ``config.yaml`` used to be logged and skipped by a read
that also skipped the package defaults beneath it, so validation died on
``comicbox.paths not found`` instead. Values under
``online.tuning.per_source`` were never type-checked, so ``auto_threshold:
high`` loaded fine and failed later, mid-lookup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from confuse import ConfigTypeError
from loguru import logger

from comicbox.config import get_config
from comicbox.config.online.settings import Effort
from comicbox.config.settings import MergeMode, parse_enum
from comicbox.exceptions import ComicboxError, ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Collect loguru warning messages."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


def _per_source(per_source: Mapping | None) -> Mapping:
    settings = get_config(
        {"comicbox": {"online": {"tuning": {"per_source": per_source}}}}
    )
    return settings.online.tuning.per_source


def test_malformed_user_config_keeps_defaults(
    tmp_path: Path, warnings: list[str]
) -> None:
    """``COMICBOXDIR`` is this test's ``tmp_path`` (tests/conftest.py)."""
    (tmp_path / "config.yaml").write_text("comicbox:\n  general: [unclosed\n")
    settings = get_config({})
    assert settings.general.jobs == 1
    assert any(msg.startswith("Ignoring user config:") for msg in warnings)


def test_config_dir_that_is_a_file_keeps_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warnings: list[str]
) -> None:
    not_a_dir = tmp_path / "file"
    not_a_dir.touch()
    monkeypatch.setenv("COMICBOXDIR", str(not_a_dir))
    settings = get_config({})
    assert settings.general.jobs == 1
    assert any("COMICBOXDIR must be a directory" in msg for msg in warnings)


def test_configuration_error_is_typed() -> None:
    """Catchable as ComicboxError, and still as the ValueError it was."""
    with pytest.raises(ConfigurationError) as exc_info:
        parse_enum(MergeMode, "--merge-mode", "sideways")
    assert isinstance(exc_info.value, ComicboxError)
    assert isinstance(exc_info.value, ValueError)


def test_per_source_values_are_type_checked() -> None:
    with pytest.raises(ConfigTypeError, match=r"per_source\.metron\.auto_threshold"):
        _per_source({"metron": {"auto_threshold": "high"}})
    with pytest.raises(ConfigTypeError, match=r"rate_limit\.per_minute"):
        _per_source({"metron": {"rate_limit": {"per_minute": "lots"}}})


def test_per_source_valid_block_loads() -> None:
    tuning = _per_source({"Metron": {"auto_threshold": 0.9, "effort": "minimal"}})
    assert tuning["metron"].auto_threshold == pytest.approx(0.9)
    assert tuning["metron"].effort == Effort.MINIMAL


def test_per_source_null_block_is_skipped() -> None:
    """Every key commented out leaves ``metron:`` null; that's not an error."""
    assert _per_source({"metron": None}) == {}


def test_per_source_unknown_source_warns(warnings: list[str]) -> None:
    assert _per_source({"metorn": {"auto_threshold": 0.9}}) == {}
    assert any("unknown source 'metorn'" in msg for msg in warnings)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("debug", "DEBUG"), (" Warning ", "WARNING"), ("INFO", "INFO"), (10, 10)],
)
def test_loglevel_names_any_case(
    tmp_path: Path, raw: str | int, expected: str | int
) -> None:
    """Level names are case-sensitive in loguru; a run used to die on ``debug``."""
    value = f'"{raw}"' if isinstance(raw, str) else raw
    (tmp_path / "config.yaml").write_text(
        f"comicbox:\n  general:\n    loglevel: {value}\n"
    )
    assert get_config({}).general.loglevel == expected


def test_loglevel_from_env_any_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", "info")
    assert get_config({}).general.loglevel == "INFO"


def test_unknown_loglevel_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", "LOUD")
    with pytest.raises(ConfigurationError, match=r"general\.loglevel.*LOUD"):
        get_config({})


def test_unknown_loglevel_exits_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from comicbox import cli

    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", "LOUD")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(("comicbox", "-p", str(tmp_path / "x.cbz")))
    assert exc_info.value.code == 1
    assert "general.loglevel" in capsys.readouterr().out


def _cli_threshold(value: str) -> float:
    from argparse import Namespace

    from comicbox.cli import get_args

    cns = get_args(["comicbox", "--auto-threshold", value, "x.cbz"])
    return get_config(Namespace(comicbox=cns)).online.tuning.auto_threshold


@pytest.mark.parametrize("value", ["95", "-1", "1.01", "nan", "inf"])
def test_auto_threshold_out_of_range_is_an_error(value: str) -> None:
    """95 (a percentage) never auto-writes; nan compares false to every score."""
    with pytest.raises(ConfigurationError, match="--auto-threshold"):
        _cli_threshold(value)


@pytest.mark.parametrize("value", ["0", "1", "0.85"])
def test_auto_threshold_in_range(value: str) -> None:
    assert _cli_threshold(value) == float(value)


def test_auto_threshold_out_of_range_from_a_config_file(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  online:\n    tuning:\n      auto_threshold: 95\n"
    )
    with pytest.raises(ConfigurationError, match=r"online\.tuning\.auto_threshold"):
        get_config({})


@pytest.mark.parametrize("value", [95, -1, float("nan")])
def test_per_source_auto_threshold_out_of_range_is_an_error(value: float) -> None:
    with pytest.raises(ConfigurationError, match=r"per_source\.metron\.auto_threshold"):
        _per_source({"metron": {"auto_threshold": value}})


@pytest.mark.parametrize("value", [0, 1, 0.85])
def test_per_source_auto_threshold_in_range(value: float) -> None:
    assert (
        _per_source({"metron": {"auto_threshold": value}})["metron"].auto_threshold
        == value
    )
