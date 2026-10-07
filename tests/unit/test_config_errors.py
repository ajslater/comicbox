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
