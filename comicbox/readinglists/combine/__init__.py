"""
Combine several lists of one reading order into one list and a report.

Pure: no files, no network. The inputs are in rank order, the first being
primary. Guarantees:

- The same inputs in the same order give the same output.
- Combining a list with itself returns it unchanged.
- Adding an input never reorders the backbone's own entries.
- A caller that wants to keep an existing order passes it first.

An entry with no key, no issue id and no series, year or volume and
number, cannot be matched, so it is never joined with another.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comicbox.exceptions import ReadingListError
from comicbox.readinglists.combine.fields import (
    is_ordered,
    merge_entry,
    merge_header,
)
from comicbox.readinglists.combine.groups import Grouping, group_rows
from comicbox.readinglists.combine.order import GroupOrderConflict, order_groups
from comicbox.readinglists.identity import entry_date, entry_sort_key
from comicbox.readinglists.schema import ENTRIES_KEY
from comicbox.readinglists.serialize import load_model


@dataclass(frozen=True, slots=True)
class EntryOrigin:
    """A row of an input: ``input_index`` ranks the input, ``row`` its entry."""

    input_index: int
    row: int


@dataclass(frozen=True, slots=True)
class OrderConflict:
    """An input puts combined entry ``entry`` somewhere the backbone does not."""

    entry: int
    input_index: int
    row: int


@dataclass(frozen=True, slots=True)
class IdConflict:
    """
    Two values for one source on one issue: one of the lists is wrong.

    Combined entry ``entry`` keeps ``kept`` for ``source``, a database; the
    row at ``input_index`` and ``row``, joined to it, had ``dropped``. A
    barcode that differs is a printing or an edition, so it is never one.
    """

    entry: int
    source: str
    kept: str
    dropped: str
    input_index: int
    row: int


@dataclass(frozen=True, slots=True)
class CombineResult:
    """
    The combined list and what combining found.

    ``provenance`` is parallel to the list's entries: the rows each came
    from, in rank order. ``only_in`` is indexed by input: the entries no
    other input has. ``name_joins`` are the entries some row joined on a
    series name alone, the joins most likely to be wrong.
    """

    reading_list: dict[str, Any]
    provenance: tuple[tuple[EntryOrigin, ...], ...]
    only_in: tuple[tuple[int, ...], ...]
    order_conflicts: tuple[OrderConflict, ...]
    id_conflicts: tuple[IdConflict, ...]
    name_joins: tuple[int, ...]


def _only_in(
    grouping: Grouping, order: Sequence[int], input_count: int
) -> tuple[tuple[int, ...], ...]:
    only_in: list[list[int]] = [[] for _ in range(input_count)]
    for position, group in enumerate(order):
        if len(members := grouping.members[group]) == 1:
            only_in[members[0][0]].append(position)
    return tuple(tuple(positions) for positions in only_in)


def _result(
    reading_list: dict[str, Any],
    grouping: Grouping,
    order: Sequence[int],
    order_conflicts: Sequence[GroupOrderConflict],
    input_count: int,
) -> CombineResult:
    position = {group: index for index, group in enumerate(order)}
    return CombineResult(
        reading_list,
        tuple(
            tuple(EntryOrigin(*node) for node in grouping.members[group])
            for group in order
        ),
        _only_in(grouping, order, input_count),
        tuple(
            OrderConflict(position[c.group], c.input_index, c.row)
            for c in order_conflicts
        ),
        tuple(
            IdConflict(
                position[c.group], c.source, c.kept, c.dropped, c.input_index, c.row
            )
            for c in grouping.id_conflicts
        ),
        tuple(sorted(position[group] for group in grouping.name_joins)),
    )


def _merge_entries(
    inputs: Sequence[Sequence[Mapping[str, Any]]], grouping: Grouping
) -> list[dict[str, Any]]:
    """Merge each group's rows into its entry, indexed by group id."""
    return [
        merge_entry([inputs[input_index][row] for input_index, row in members])
        for members in grouping.members
    ]


def _order(
    grouping: Grouping, entries: Sequence[Mapping[str, Any]], flags: Sequence[bool]
) -> tuple[list[int], list[GroupOrderConflict]]:
    """Order the groups by the ordered inputs, then by date."""
    return order_groups(
        grouping.sequences,
        flags,
        [entry_sort_key(entry) for entry in entries],
        [entry_date(entry) for entry in entries],
    )


def combine(reading_lists: Sequence[Mapping[str, Any]]) -> CombineResult:
    """
    Combine lists of one reading order, given in rank order.

    Rows are the same issue when they share an ``entry_keys`` key. The
    first ordered input is the backbone of the order; an entry's fields are
    the union of ids and otherwise the first value in rank order.
    """
    if not reading_lists:
        reason = "Nothing to combine."
        raise ReadingListError(reason)
    lists = [load_model(reading_list) for reading_list in reading_lists]
    inputs = [reading_list.get(ENTRIES_KEY) or [] for reading_list in lists]
    grouping = group_rows(inputs)
    entries = _merge_entries(inputs, grouping)
    flags = [is_ordered(reading_list) for reading_list in lists]
    order, order_conflicts = _order(grouping, entries, flags)
    backbone = flags.index(True) if True in flags else None
    # Built only from model-loaded values, so it needs no second load.
    reading_list = merge_header(lists, backbone)
    if order:
        reading_list[ENTRIES_KEY] = [entries[group] for group in order]
    return _result(reading_list, grouping, order, order_conflicts, len(lists))
