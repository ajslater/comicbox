"""
Which rows of several lists are the same issue.

Every row is a node ``(input index, row index)`` carrying its
``entry_keys``. A key is qualified by how many earlier rows of its own input
carry it, so the first occurrence of a repeated issue lines up with the
first in another list and the second with the second, and two rows of one
input never share a qualified key. Rows that share a qualified key are
joined with a union-find, so a ComicVine id joining A and B and a Metron id
joining B and C put all three together.
"""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.readinglists.identity import (
    ID_KEY_KIND,
    NAME_KEY_KIND,
    EntryKey,
    entry_keys,
)

Node = tuple[int, int]
QualifiedKey = tuple[EntryKey, int]

# A barcode differing between two rows of one issue is a variant cover, a
# printing or an edition, not a bad mapping.
_BARCODE_SOURCES = frozenset(
    {
        IdSources.ASIN.value,
        IdSources.GTIN.value,
        IdSources.ISBN.value,
        IdSources.UPC.value,
    }
)


@dataclass(frozen=True, slots=True)
class GroupIdConflict:
    """Two values for one source in one group; ``group`` is a group id."""

    group: int
    source: str
    kept: str
    dropped: str
    input_index: int
    row: int


@dataclass(frozen=True, slots=True)
class Grouping:
    """
    The groups of rows that are the same issue.

    Group ids number the groups by first appearance, reading the inputs in
    rank order. ``members`` holds each group's nodes in rank order, at most
    one per input. ``sequences`` holds each input's group ids in row order.
    """

    members: tuple[tuple[Node, ...], ...]
    sequences: tuple[tuple[int, ...], ...]
    id_conflicts: tuple[GroupIdConflict, ...]
    name_joins: frozenset[int]


class _UnionFind:
    """Disjoint sets of nodes; the smallest node is a set's root."""

    __slots__ = ("_parent",)

    def __init__(self) -> None:
        self._parent: dict[Node, Node] = {}

    def find(self, node: Node) -> Node:
        """Return the node's root, compressing the path to it."""
        root = node
        while (parent := self._parent.setdefault(root, root)) != root:
            root = parent
        while node != root:
            node, self._parent[node] = self._parent[node], root
        return root

    def union(self, one: Node, other: Node) -> None:
        """Join two nodes' sets."""
        roots = sorted((self.find(one), self.find(other)))
        self._parent[roots[1]] = roots[0]


def _qualify(entries: Sequence[Mapping[str, Any]]) -> list[list[QualifiedKey]]:
    """Each row's keys, qualified by their count in earlier rows."""
    counts: Counter[EntryKey] = Counter()
    qualified = []
    for entry in entries:
        keys = entry_keys(entry)
        qualified.append([(key, counts[key]) for key in keys])
        counts.update(keys)
    return qualified


def _nodes(qualified: Sequence[Sequence[Sequence[QualifiedKey]]]) -> Iterator[Node]:
    for input_index, rows in enumerate(qualified):
        for row in range(len(rows)):
            yield (input_index, row)


def _join(
    qualified: Sequence[Sequence[Sequence[QualifiedKey]]],
    apart: frozenset[Node],
) -> list[list[Node]]:
    """Group the nodes that share a qualified key; keep ``apart`` alone."""
    union_find = _UnionFind()
    holders: dict[QualifiedKey, Node] = {}
    for node in _nodes(qualified):
        union_find.find(node)
        if node in apart:
            continue
        for key in qualified[node[0]][node[1]]:
            if (holder := holders.setdefault(key, node)) != node:
                union_find.union(holder, node)
    groups: dict[Node, list[Node]] = {}
    for node in _nodes(qualified):
        groups.setdefault(union_find.find(node), []).append(node)
    return list(groups.values())


def _later_rows_of_one_input(groups: list[list[Node]]) -> dict[Node, list[Node]]:
    """Map each row a chain put beside an earlier row of its input to its group."""
    later: dict[Node, list[Node]] = {}
    for members in groups:
        inputs_seen: set[int] = set()
        for node in members:
            if node[0] in inputs_seen:
                later[node] = members
            inputs_seen.add(node[0])
    return later


def _key_source(key: EntryKey) -> str:
    return key[1] if key[0] == ID_KEY_KIND else NAME_KEY_KIND


def _key_value(key: EntryKey) -> str:
    if key[0] == ID_KEY_KIND:
        return str(key[2])
    _, series, discriminator, number, suffix = key
    number = "" if number is None else number
    return f"{series} ({discriminator}) #{number}{suffix}"


class _Grouper:
    """Group the rows of ranked inputs and report what disagreed."""

    def __init__(self, inputs: Sequence[Sequence[Mapping[str, Any]]]) -> None:
        """Qualify every row's keys."""
        self._qualified = [_qualify(entries) for entries in inputs]
        self._conflicts: list[GroupIdConflict] = []

    def _keys(self, node: Node) -> list[QualifiedKey]:
        return self._qualified[node[0]][node[1]]

    def _id_keys(self, node: Node) -> list[QualifiedKey]:
        return [qkey for qkey in self._keys(node) if qkey[0][0] == ID_KEY_KIND]

    def _group_value(self, members: Sequence[Node], source: str) -> str:
        """Get the value the best ranked member holds for a source."""
        for member in members:
            for key, _ in self._keys(member):
                if _key_source(key) == source:
                    return _key_value(key)
        return ""

    def _record_split(
        self,
        node: Node,
        first_pass: Sequence[Node],
        groups: Sequence[Sequence[Node]],
        group_of: Mapping[Node, int],
    ) -> None:
        """Report a row kept apart, by the key that had linked it."""
        others = {
            qkey
            for member in first_pass
            if member != node
            for qkey in self._keys(member)
        }
        key = next(key for key, n in self._keys(node) if (key, n) in others)
        earliest = next(member for member in first_pass if member[0] == node[0])
        group = group_of[earliest]
        source = _key_source(key)
        kept = self._group_value(groups[group], source)
        self._conflicts.append(
            GroupIdConflict(group, source, kept, _key_value(key), *node)
        )

    def _record_disagreements(self, group: int, members: Sequence[Node]) -> None:
        """Keep the best ranked id per database and report the others."""
        kept: dict[str, str] = {}
        for member in members:
            for (_, source, value), _ in self._id_keys(member):
                first = kept.setdefault(source, value)
                if first != value and source not in _BARCODE_SOURCES:
                    self._conflicts.append(
                        GroupIdConflict(group, source, first, value, *member)
                    )

    def _is_name_join(self, members: Sequence[Node]) -> bool:
        """Whether some member is in the group by a name key alone."""
        if len(members) < 2:  # noqa: PLR2004
            return False
        counts = Counter(qkey for member in members for qkey in self._id_keys(member))
        return any(
            all(counts[qkey] < 2 for qkey in self._id_keys(member))  # noqa: PLR2004
            for member in members
        )

    def _sequences(self, group_of: Mapping[Node, int]) -> tuple[tuple[int, ...], ...]:
        return tuple(
            tuple(group_of[input_index, row] for row in range(len(rows)))
            for input_index, rows in enumerate(self._qualified)
        )

    def group(self) -> Grouping:
        """Join, keep later rows of one input apart, then report."""
        first_pass = _join(self._qualified, frozenset())
        later = _later_rows_of_one_input(first_pass)
        groups = _join(self._qualified, frozenset(later)) if later else first_pass
        groups.sort(key=lambda members: members[0])
        group_of = {
            node: index for index, members in enumerate(groups) for node in members
        }
        for node in sorted(later):
            self._record_split(node, later[node], groups, group_of)
        name_joins = set()
        for index, members in enumerate(groups):
            self._record_disagreements(index, members)
            if self._is_name_join(members):
                name_joins.add(index)
        return Grouping(
            tuple(tuple(members) for members in groups),
            self._sequences(group_of),
            tuple(self._conflicts),
            frozenset(name_joins),
        )


def group_rows(inputs: Sequence[Sequence[Mapping[str, Any]]]) -> Grouping:
    """Group the rows of lists, in rank order, that are the same issue."""
    return _Grouper(inputs).group()
