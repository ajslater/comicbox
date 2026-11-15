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


class _OrderedInsert:
    """
    Insert an ordered input's new groups beside the entries both lists hold.

    A new group goes after the nearest preceding entry of the longest common
    subsequence; with none before it, just before the first one; with no
    common entry at all, after the merged entries. A shared entry outside
    the subsequence is where the two orders disagree, so it is recorded and
    left where it is.
    """

    def __init__(
        self, merged: Sequence[int], sequence: Sequence[int], input_index: int
    ) -> None:
        self._merged = merged
        self._sequence = sequence
        self._input_index = input_index
        self._present = set(merged)
        self._insertions: dict[int, list[int]] = {}
        self.conflicts: list[GroupOrderConflict] = []
        # None until the first common entry: groups before it wait for it.
        self._anchor: int | None = None
        self._waiting: list[int] = []

    def _common(self, src_start: int, src_end: int) -> None:
        if self._anchor is None and self._waiting:
            self._insertions[src_start] = self._waiting
        self._anchor = src_end

    def _place(self, row: int) -> None:
        group = self._sequence[row]
        if group in self._present:
            self.conflicts.append(GroupOrderConflict(group, self._input_index, row))
        elif self._anchor is None:
            self._waiting.append(group)
        else:
            self._insertions.setdefault(self._anchor, []).append(group)

    def run(self) -> list[int]:
        """Return the merged groups with this input's new ones inserted."""
        for opcode in LCSseq.opcodes(self._merged, self._sequence):
            if opcode.tag == _EQUAL:
                self._common(opcode.src_start, opcode.src_end)
                continue
            for row in range(opcode.dest_start, opcode.dest_end):
                self._place(row)
        if self._anchor is None and self._waiting:
            self._insertions[len(self._merged)] = self._waiting
        return _rebuild(self._merged, self._insertions)


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
        insert = _OrderedInsert(merged, sequences[input_index], input_index)
        merged = insert.run()
        conflicts.extend(insert.conflicts)
    for input_index, flag in enumerate(ordered):
        if not flag:
            merged = _insert_unordered(merged, sequences[input_index], sort_keys, dates)
    return merged, conflicts
