"""Not that respects zero."""
from collections.abc import Iterable
from typing import Any


def is_empty(value: dict[str, None]|dict[str, dict[Any, Any]]|int|str) -> bool:
    """Test for emptiness."""
    return not value and value != 0


def not_is_empty(value: dict[str|Any, dict[str, str]|int|str|Any]) -> bool:
    """Nevative is empty."""
    return not is_empty(value)


def filter_list_empty(lst: list[dict[str, int]|dict[str, str]|dict[Any, Any]|Any]) -> Iterable:
    """Filter list for empties, returns iterator."""
    return filter(not_is_empty, lst)
