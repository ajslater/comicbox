"""Not that respects zero."""

from collections.abc import Iterable


def is_empty(value) -> bool:
    """Test for emptiness."""
    return not value and value != 0


def not_is_empty(value) -> bool:
    """Nevative is empty."""
    return not is_empty(value)


def filter_list_empty(lst) -> Iterable:
    """Filter list for empties, returns iterator."""
    return filter(not_is_empty, lst)
