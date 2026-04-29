"""Logging classes."""

import os
import sys
from pathlib import Path

from loguru import logger  # noqa: F401
from typing_extensions import Any

DEBUG = os.environ.get("DEBUG", "")


def _log_format() -> str:
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
_initialized_key: tuple[str | int, str | None, Any] | None = None


def _resolve_sink(sink: Any) -> Any:
    """Resolve a string sink name to a file object; pass through otherwise."""
    if sink is None or sink == "stdout":
        return sys.stdout
    if sink == "stderr":
        return sys.stderr
    if isinstance(sink, (str, Path)):
        return Path(sink)
    return sink


def init_logging(
    loglevel: str | int = "INFO",
    logger_: Any = None,
    log_format: str | None = None,
    sink: Any = None,
) -> None:
    """
    Initialize logging.

    sink: "stdout", "stderr", a file path (str|Path), or any loguru-compatible
        sink. Defaults to sys.stdout. Strings are preferred over file objects
        when this config will travel across processes (file objects don't pickle).
    """
    global _initialized_key  # noqa: PLW0603

    if logger_:
        global logger  # noqa: PLW0603
        logger = logger_
        _initialized_key = (loglevel, log_format, sink)
        return

    key = (loglevel, log_format, sink)
    if _initialized_key == key:
        return

    logger.level("DEBUG", color="<light-black>")
    logger.level("INFO", color="<white>")
    logger.level("SUCCESS", color="<green>")

    fmt = log_format if log_format is not None else _log_format()
    kwargs: dict[str, Any] = {
        "level": loglevel,
        "backtrace": True,
        "catch": True,
        "format": fmt,
        "enqueue": True,
    }

    logger.remove()  # Default "sys.stderr" sink is not picklable
    logger.add(_resolve_sink(sink), **kwargs)
    _initialized_key = key
