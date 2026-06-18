"""Logging classes."""

import os
import sys
from pathlib import Path

from loguru import logger
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
    log_format: str | None = None,
    sink: Any = None,
) -> None:
    """
    Initialize logging for comicbox EXECUTABLE entry points.

    Replaces every configured loguru sink with comicbox's own, so this must
    only run from processes comicbox owns (the CLI Runner, worker
    initializers, scripts) — never from library code. Library consumers
    configure loguru themselves; comicbox modules log through whatever
    sinks the host application set up.

    sink: "stdout", "stderr", a file path (str|Path), or any loguru-compatible
        sink. Defaults to sys.stdout. Strings are preferred over file objects
        when this config will travel across processes (file objects don't pickle).
    """
    global _initialized_key  # noqa: PLW0603

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
        # diagnose=True renders each frame's local variables on
        # logger.exception(...), which leaks api_key / password strings
        # held as locals in our online-source frames (and in simyan /
        # mokkari frames we can't modify). Keep this off.
        "diagnose": False,
        "catch": True,
        "format": fmt,
        "enqueue": True,
    }

    logger.remove()  # Default "sys.stderr" sink is not picklable
    logger.add(_resolve_sink(sink), **kwargs)
    _initialized_key = key
