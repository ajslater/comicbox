"""Wrapped marshmallow decorators."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from loguru import logger


def trap_error(decorator: Callable) -> Callable[[Callable], Callable]:
    """Wrap marshmallow decorators to trap exceptions and log them."""

    def wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapped(self: Any, data: Any, **kwargs: Any) -> Any:
            try:
                return func(self, data, **kwargs)
            except Exception:
                logger.exception(func.__name__)
                return data

        return decorator(wrapped)

    return wrapper
