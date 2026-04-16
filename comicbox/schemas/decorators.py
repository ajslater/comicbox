"""Wrapped marshmallow decorators."""
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import collections.abc
    import datetime
    import types

    import ruamel.yaml

    import comicbox.schemas.comicbox.publishing

from functools import wraps

from loguru import logger


def trap_error(decorator: "Callable[[collections.abc.Callable[..., Any]|None, bool], collections.abc.Callable[..., Any]]") -> Callable[[Callable], Callable]:
    """Wrap marshmallow decorators to trap exceptions and log them."""

    def wrapper(func: "Callable[..., dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, dict[str, str]]]]|dict[str, dict[str, dict[str, dict[Any, Any]]]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, list[str]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, str]|dict[Any, Any]|ruamel.yaml.CommentedMap]") -> "Callable[..., dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[int, dict[str, None]]]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, dict[str, str]]]]|dict[str, dict[str, dict[str, dict[Any, Any]]]]|dict[str, dict[str, dict[str, list[Any]]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, set[str]]|dict[str, str]|dict[Any, Any]|ruamel.yaml.CommentedMap]":
        @wraps(func)
        def wrapped(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", data: "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[str, list[dict[str, str]]]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, int]]|dict[str, dict[str, set[str]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[dict[str, str]]]|dict[str, set[str]]|dict[str, str]|ruamel.yaml.CommentedMap|types.MappingProxyType[str, dict[str, dict[str, int]]]|types.MappingProxyType[str, dict[str, dict[str, list[dict[str, str]]]]]|None", **kwargs: bool|str) -> "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[int, dict[str, None]]]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, dict[str, str]]]]|dict[str, dict[str, dict[str, dict[Any, Any]]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, int]]|dict[str, dict[str, list[dict[str, dict[str, None]]]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[dict[str, str]]]|dict[str, set[str]]|dict[str, str]|dict[Any, Any]|ruamel.yaml.CommentedMap|types.MappingProxyType[str, dict[str, dict[str, int]]]|types.MappingProxyType[str, dict[str, dict[str, str]]]":
            try:
                return func(self, data, **kwargs)
            except Exception:
                logger.exception(func.__name__)
                return data

        return decorator(wrapped)

    return wrapper
