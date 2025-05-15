"""Logging classes."""

import os
from logging import INFO, basicConfig, root

from rich.logging import RichHandler

DATEFMT = "%Y-%m-%d %H:%M:%S %Z"
LOG_FMT = "%(message)s"


def init_logging(loglevel=INFO):
    """Initialize logging."""
    if root.handlers:
        # Do not reinintialize if logging is already set up
        return

    level = os.environ.get("LOGLEVEL", loglevel)

    handler = RichHandler(rich_tracebacks=True)
    basicConfig(level=level, format=LOG_FMT, datefmt=DATEFMT, handlers=[handler])
