"""Wrapped marshmallow decorators."""

from functools import wraps
from logging import getLogger

LOG = getLogger(__name__)


def trap_error(decorator):
    """Wrap marshmallow decorators to trap exceptions and log them."""

    def wrapper(func):
        @wraps(func)
        def wrapped(self, data, **kwargs):
            try:
                return func(self, data, **kwargs)
            except Exception:
                LOG.exception(func.__name__)
                return data

        return decorator(wrapped)

    return wrapper
