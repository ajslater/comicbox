"""Wrapped marshmallow decorators."""

from functools import wraps

from loguru import logger


def trap_error(decorator):
    """Wrap marshmallow decorators to trap exceptions and log them."""

    def wrapper(func):
        @wraps(func)
        def wrapped(self, data, **kwargs):
            try:
                return func(self, data, **kwargs)
            except Exception:
                logger.exception(func.__name__)
                return data

        return decorator(wrapped)

    return wrapper
