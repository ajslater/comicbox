"""
Name what a format changes: the model paths a round trip does not keep.

``lost_fields`` writes a list, reads it back and compares, so its answer
is exact by construction: every path on which the list read back differs
from the list written is named, and nothing else. A flag at its default
is the same as a flag left out.
"""

from collections.abc import Iterable, Mapping, Sequence
from itertools import zip_longest
from types import MappingProxyType
from typing import Any

from comicbox.readinglists.schema import (
    ENTRIES_KEY,
    IDENTIFIERS_KEY,
    ORDERED_KEY,
    PRIVATE_KEY,
)

# A list is ordered and public unless it says otherwise.
_FLAG_DEFAULTS = MappingProxyType({ORDERED_KEY: True, PRIVATE_KEY: False})


def skipped_entries(positions: Iterable[int]) -> str:
    """Name entries by their position from 0, as a person counts them."""
    return f"{ENTRIES_KEY} " + ", ".join(f"#{position + 1}" for position in positions)


def _header(reading_list: Mapping[str, Any]) -> dict[str, Any]:
    header = {key: value for key, value in reading_list.items() if key != ENTRIES_KEY}
    for key, default in _FLAG_DEFAULTS.items():
        header.setdefault(key, default)
    return header


def _leaves(data: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    """Flatten an entry to its paths, each identifier whole."""
    leaves: dict[str, Any] = {}
    for key, value in data.items():
        here = f"{prefix}.{key}"
        if key == IDENTIFIERS_KEY and isinstance(value, Mapping):
            leaves.update({f"{here}.{source}": item for source, item in value.items()})
        elif isinstance(value, Mapping):
            leaves.update(_leaves(value, here))
        else:
            leaves[here] = value
    return leaves


def _different(before: Mapping[str, Any], after: Mapping[str, Any]) -> set[str]:
    return {
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    }


def describe_losses(
    before: Mapping[str, Any], after: Mapping[str, Any], skipped: Sequence[int]
) -> tuple[str, ...]:
    """
    Name the paths on which ``after`` differs from ``before``.

    Header keys come first, then entry paths such as
    ``entries.date.cover_date`` for any entry, then ``entries #2, #5`` for
    the entries ``skipped`` names, which were not written at all.
    """
    lost = sorted(_different(_header(before), _header(after)))
    kept = [
        entry
        for position, entry in enumerate(before.get(ENTRIES_KEY) or ())
        if position not in skipped
    ]
    paths: set[str] = set()
    for entry, entry_back in zip_longest(
        kept, after.get(ENTRIES_KEY) or (), fillvalue={}
    ):
        paths |= _different(
            _leaves(entry, ENTRIES_KEY), _leaves(entry_back, ENTRIES_KEY)
        )
    lost.extend(sorted(paths))
    if skipped:
        lost.append(skipped_entries(skipped))
    return tuple(lost)
