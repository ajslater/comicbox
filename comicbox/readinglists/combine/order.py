"""
Put the groups of several lists in one reading order.

The tokens are group ids. The first ordered input is the backbone, and
nothing ever moves one of its entries: further ordered inputs only insert
the groups the merged sequence lacks, unordered inputs place theirs by date,
and with no ordered input everything sorts by date.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from rapidfuzz.distance import LCSseq

_EQUAL = "equal"


@dataclass(frozen=True, slots=True)
class GroupOrderConflict:
    """A shared group an input puts elsewhere; ``group`` is a group id."""

    group: int
    input_index: int
    row: int


def _rebuild(merged: Sequence[int], insertions: dict[int, list[int]]) -> list[int]:
    """Insert groups before the merged positions they are keyed by."""
    result: list[int] = []
    for position, group in enumerate(merged):
        result.extend(insertions.get(position, ()))
        result.append(group)
    result.extend(insertions.get(len(merged), ()))
    return result


def _insert_ordered(
    merged: list[int], sequence: Sequence[int], input_index: int
) -> tuple[list[int], list[GroupOrderConflict]]:
    """
    Insert an ordered input's new groups after their nearest common anchor.

    The anchor is the nearest preceding entry in the longest common
    subsequence, not any shared entry: a shared entry outside it is where
    the two orders disagree, so it is recorded and left where it is.
    """
    present = set(merged)
    insertions: dict[int, list[int]] = {}
    conflicts: list[GroupOrderConflict] = []
    anchor = 0
    for opcode in LCSseq.opcodes(merged, sequence):
        if opcode.tag == _EQUAL:
            anchor = opcode.src_end
            continue
        for row in range(opcode.dest_start, opcode.dest_end):
            group = sequence[row]
            if group in present:
                conflicts.append(GroupOrderConflict(group, input_index, row))
            else:
                insertions.setdefault(anchor, []).append(group)
    return _rebuild(merged, insertions), conflicts


def _date_positions(
    merged: Sequence[int], new: Sequence[int], dates: Sequence[date | None]
) -> dict[int, list[int]]:
    """
    Key each dated new group by where it goes among the merged groups.

    After the last merged group dated on or before it; before the first
    dated one if all are later; at the end if none is dated. ``new`` is in
    date order, so one sweep finds every position.
    """
    dated = sorted(
        (when, position)
        for position, group in enumerate(merged)
        if (when := dates[group]) is not None
    )
    first_dated = min((position for _, position in dated), default=len(merged))
    insertions: dict[int, list[int]] = {}
    last = -1
    cursor = 0
    for group in new:
        when = dates[group]
        while cursor < len(dated) and when is not None and dated[cursor][0] <= when:
            last = max(last, dated[cursor][1])
            cursor += 1
        position = last + 1 if last >= 0 else first_dated
        insertions.setdefault(position, []).append(group)
    return insertions


def _insert_unordered(
    merged: list[int],
    sequence: Sequence[int],
    sort_keys: Sequence[tuple[Any, ...]],
    dates: Sequence[date | None],
) -> list[int]:
    """Place an unordered input's new groups by date; undated ones go last."""
    present = set(merged)
    new = [group for group in sequence if group not in present]
    dated = sorted(
        (group for group in new if dates[group] is not None),
        key=lambda group: sort_keys[group],
    )
    undated = [group for group in new if dates[group] is None]
    return _rebuild(merged, _date_positions(merged, dated, dates)) + undated


def order_groups(
    sequences: Sequence[Sequence[int]],
    ordered: Sequence[bool],
    sort_keys: Sequence[tuple[Any, ...]],
    dates: Sequence[date | None],
) -> tuple[list[int], list[GroupOrderConflict]]:
    """
    Order every group, given each input's sequence of groups in rank order.

    ``sort_keys`` and ``dates`` are indexed by group id. Returns the group
    ids in reading order and the order conflicts.
    """
    ordered_inputs = [index for index, flag in enumerate(ordered) if flag]
    if not ordered_inputs:
        # Group ids number groups by first appearance, the last tiebreak.
        return sorted(range(len(sort_keys)), key=lambda g: (sort_keys[g], g)), []
    merged = list(sequences[ordered_inputs[0]])
    conflicts: list[GroupOrderConflict] = []
    for input_index in ordered_inputs[1:]:
        merged, found = _insert_ordered(merged, sequences[input_index], input_index)
        conflicts.extend(found)
    for input_index, flag in enumerate(ordered):
        if not flag:
            merged = _insert_unordered(merged, sequences[input_index], sort_keys, dates)
    return merged, conflicts
