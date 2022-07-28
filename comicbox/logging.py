"""Logging classes."""
import logging
import os

from logging import Formatter, StreamHandler, basicConfig

from colors import color


DATEFMT = "%Y-%m-%d %H:%M:%S %Z"
LOG_FMT = "{asctime} {levelname:8} {message}"


class ColorFormatter(Formatter):
    """Logging Formatter to add colors and count warning / errors."""

    FORMAT_COLORS = {
        "CRITICAL": {"fg": "red", "style": "bold"},
        "ERROR": {"fg": "red"},
        "WARNING": {"fg": "yellow"},
        "INFO": {"fg": "green"},
        "DEBUG": {"fg": "black", "style": "bold"},
        "NOTSET": {"fg": "blue"},
    }

    FORMATTERS = {}

    def __init__(self, format, **kwargs):
        """Set up formatters."""
        super().__init__(**kwargs)
        for level_name, args in self.FORMAT_COLORS.items():
            levelno = getattr(logging, level_name)
            template = color(format, **args)
            self.FORMATTERS[levelno] = Formatter(fmt=template, **kwargs)

    def format(self, record):
        """Format each log message."""
        formatter = self.FORMATTERS[record.levelno]
        return formatter.format(record)


def init_logging():
    """Initialize logging."""
    level = os.environ.get("LOGLEVEL", logging.INFO)

    formatter = ColorFormatter(LOG_FMT, style="{", datefmt=DATEFMT)

    handler = StreamHandler()
    handler.setFormatter(formatter)
    basicConfig(level=level, handlers=[handler])
