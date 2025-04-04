"""Deep empty cleaner."""

from collections.abc import Iterable, Mapping
from decimal import Decimal


def is_empty(value, mapping_ok: bool = False) -> bool:  # noqa: FBT002
    """Test for emptiness."""
    return (
        not value
        and not isinstance(value, int | Decimal | float)
        and not (mapping_ok and isinstance(value, Mapping))
    )


def not_is_empty(value) -> bool:
    """Nevative is empty."""
    return not is_empty(value)


def filter_list_empty(lst) -> Iterable:
    """Filter list for empties, returns iterator."""
    return filter(not_is_empty, lst)


def filter_map_empty(m, mapping_ok: bool = False) -> dict:  # noqa: FBT002
    """Filter map for empties."""
    return {k: v for k, v in m.items() if not (is_empty(k) or is_empty(v, mapping_ok))}
