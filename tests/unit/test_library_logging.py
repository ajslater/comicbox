"""Library-logging contract: constructing a Comicbox must not touch loguru."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.box import Comicbox
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_cbz(tmp_path: Path) -> Path:
    """Fresh copy of the test CBZ for each test."""
    target = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, target)
    return target


def test_constructor_preserves_host_loguru_sinks(tmp_cbz: Path) -> None:
    """
    A host application's configured sinks survive Comicbox construction.

    Comicbox used to call init_logging() from __init__, which ran
    logger.remove() and deleted every sink the host had configured.
    """
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="INFO", format="{message}")
    try:
        with Comicbox(tmp_cbz) as cb:
            cb.get_file_type()
        logger.info("sentinel-after-comicbox-init")
        assert any("sentinel-after-comicbox-init" in m for m in messages)
    finally:
        logger.remove(handler_id)
