"""Cache for marshmallow schema instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from comicbox.formats.base.schemas.base import BaseSchema

_schema_cache: dict[tuple, BaseSchema] = {}


_EMPTY_FROZENSET: frozenset = frozenset()


def get_schema(
    cls: type[BaseSchema],
    path: Path | str | None = None,
    exclude: frozenset | tuple | set = _EMPTY_FROZENSET,
) -> BaseSchema:
    """Get a cached schema instance, creating one if needed."""
    key = (cls, frozenset(exclude) if exclude else frozenset())
    if key not in _schema_cache:
        _schema_cache[key] = cls(path=path, exclude=exclude)
    schema = _schema_cache[key]
    # Safe on a shared cached instance: set_path writes a thread-local
    # ContextVar (the warning-prefix path), not instance state, so
    # concurrent -j N workers don't relabel each other's warnings.
    schema.set_path(path)
    return schema
