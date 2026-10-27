"""mokkari logs through the standard library; the CLI routes it into loguru."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.logger import _intercept_stdlib_loggers

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def messages() -> Iterator[list[str]]:
    """Collect loguru output, and restore the stdlib `mokkari` logger after."""
    stdlib_logger = logging.getLogger("mokkari")
    saved = (stdlib_logger.handlers[:], stdlib_logger.level, stdlib_logger.propagate)
    collected: list[str] = []
    handler_id = logger.add(collected.append, level="DEBUG", format="{level} {message}")
    yield collected
    logger.remove(handler_id)
    stdlib_logger.handlers, stdlib_logger.level, stdlib_logger.propagate = saved


def test_mokkari_warnings_reach_loguru(messages: list[str]) -> None:
    """A cache failure is a comicbox log line, not a stray stderr print."""
    _intercept_stdlib_loggers("INFO")
    logging.getLogger("mokkari.sqlite_cache").warning("Couldn't enable WAL: %r", "x")
    assert messages == ["WARNING Couldn't enable WAL: 'x'\n"]


def test_mokkari_follows_the_comicbox_level(messages: list[str]) -> None:
    """
    Below comicbox's level a record isn't even made.

    mokkari attaches a traceback to a cache failure only when DEBUG is
    enabled, so this keeps tracebacks out of an INFO run.
    """
    _intercept_stdlib_loggers("INFO")
    mokkari_logger = logging.getLogger("mokkari.session")
    mokkari_logger.debug("Cache hit: /issue/1/")
    assert messages == []
    assert not mokkari_logger.isEnabledFor(logging.DEBUG)

    _intercept_stdlib_loggers("DEBUG")
    mokkari_logger.debug("Cache hit: /issue/1/")
    assert messages == ["DEBUG Cache hit: /issue/1/\n"]
