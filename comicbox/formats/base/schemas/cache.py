"""Cache for marshmallow schema instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    from pathlib import Path

from comicbox.formats.base.schemas.error_store import ClearingErrorStoreSchema

_SchemaT = TypeVar("_SchemaT", bound=ClearingErrorStoreSchema)

_schema_cache: dict[tuple, ClearingErrorStoreSchema] = {}


_EMPTY_FROZENSET: frozenset = frozenset()


def get_schema(
    cls: type[_SchemaT],
    path: Path | str | None = None,
    exclude: frozenset | tuple | set = _EMPTY_FROZENSET,
) -> _SchemaT:
    """Get a cached schema instance, creating one if needed."""
    key = (cls, frozenset(exclude) if exclude else frozenset())
    if key not in _schema_cache:
        _schema_cache[key] = cls(path=path, exclude=exclude)
    # The key names the class, so the instance filed under it is one.
    schema = cast("_SchemaT", _schema_cache[key])
    # Safe on a shared cached instance: set_path writes a thread-local
    # ContextVar (the warning-prefix path), not instance state, so
    # concurrent -j N workers don't relabel each other's warnings.
    schema.set_path(path)
    return schema
