"""Logging classes."""

import logging
import os
from logging import INFO, Formatter, StreamHandler, basicConfig
from types import MappingProxyType

from colors import color

DATEFMT = "%Y-%m-%d %H:%M:%S %Z"
LOG_FMT = "{asctime} {levelname:8} {message}"


class ColorFormatter(Formatter):
    """Logging Formatter to add colors and count warning / errors."""

    FORMAT_COLORS = MappingProxyType(
        {
            "CRITICAL": {"fg": "red", "style": "bold"},
            "ERROR": {"fg": "red"},
            "WARNING": {"fg": "yellow"},
            "INFO": {"fg": "green"},
            "DEBUG": {"fg": "black", "style": "bold"},
            "NOTSET": {"fg": "blue"},
        }
    )

    def __init__(self, log_format, **kwargs):
        """Set up formatters."""
        super().__init__(**kwargs)
        self.formatters = {}
        for level_name, args in self.FORMAT_COLORS.items():
            levelno = getattr(logging, level_name)
            template = color(log_format, **args)
            self.formatters[levelno] = Formatter(fmt=template, **kwargs)

    def format(self, record):
        """Format each log message."""
        formatter = self.formatters[record.levelno]
        return formatter.format(record)


def init_logging(loglevel=INFO):
    """Initialize logging."""
    level = os.environ.get("LOGLEVEL", loglevel)

    formatter = ColorFormatter(LOG_FMT, style="{", datefmt=DATEFMT)

    handler = StreamHandler()
    handler.setFormatter(formatter)
    basicConfig(level=level, handlers=[handler])
