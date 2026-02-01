"""Logging classes."""

import os
import sys

from loguru import logger  # noqa: F401
from typing_extensions import Any

DEBUG = os.environ.get("DEBUG", "")


def _log_format():
    fmt = "<lvl>{time:YYYY-MM-DD HH:mm:ss} | {level: <8}"
    if DEBUG:
        fmt += " | </lvl>"
        fmt += "<dim><cyan>{thread.name}</cyan></dim>:"
        fmt += "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
        fmt += "<lvl>"
    fmt += " | {message}</lvl>"
    # fmt += "\n{exception}"  only for format as a callable
    return fmt


_LOG_FORMAT = _log_format()


def init_logging(loglevel: str = "INFO", logger_=None):
    """Initialize logging."""
    if logger_:
        global logger  # noqa: PLW0603
        logger = logger_
        return

    logger.level("DEBUG", color="<light-black>")
    logger.level("INFO", color="<white>")
    logger.level("SUCCESS", color="<green>")

    log_format = _log_format()
    kwargs: dict[str, Any] = {
        "level": loglevel,
        "backtrace": True,
        "catch": True,
        "format": log_format,
    }

    logger.remove()  # Default "sys.stderr" sink is not picklable
    logger.add(sys.stdout, **kwargs)
