"""
Which rows of several lists are the same issue.

Every row is a node ``(input index, row index)`` carrying its
``entry_keys``. A key is qualified by how many earlier rows of its own input
carry it, so the first occurrence of a repeated issue lines up with the
first in another list and the second with the second, and two rows of one
input never share a qualified key.

Two rows of different inputs that share a qualified key are linked, and
links join groups transitively: a ComicVine id joining A and B and a Metron
id joining B and C put all three together. Links are applied strongest
first, ids in ``ranked_id_sources`` order, then names with a start year or
volume, then names with a cover year, and within one strength by input
rank and row. A link that would put two rows of one input in one group is
refused, so a name match never takes a row an id match wanted, nor a
cover-year match one a name match wanted, and nothing is cut apart
afterwards.
"""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.identifiers import ID_SOURCE_VALUES
from comicbox.readinglists.identity import (
    ID_KEY_KIND,
    NAME_YEAR_KEY_KIND,
    EntryKey,
    entry_keys,
)

Node = tuple[int, int]
QualifiedKey = tuple[EntryKey, int]
_Link = tuple[tuple[int, int], Node, Node]

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
_ID_SOURCE_RANKS = {source: rank for rank, source in enumerate(ID_SOURCE_VALUES)}
_NAME_STRENGTH = (1, 0)
_NAME_YEAR_STRENGTH = (2, 0)


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


class _Groups:
    """Disjoint sets of nodes, each holding at most one row per input."""

    __slots__ = ("_inputs", "_parent")

    def __init__(self, nodes: Sequence[Node]) -> None:
        self._parent: dict[Node, Node] = {node: node for node in nodes}
        self._inputs: dict[Node, set[int]] = {node: {node[0]} for node in nodes}

    def find(self, node: Node) -> Node:
        """Return the node's root, compressing the path to it."""
        root = node
        while (parent := self._parent[root]) != root:
            root = parent
        while node != root:
            node, self._parent[node] = self._parent[node], root
        return root

    def link(self, one: Node, other: Node) -> None:
        """Join two nodes' groups, unless both hold a row of one input."""
        roots = sorted((self.find(one), self.find(other)))
        root, child = roots
        if root == child or self._inputs[root] & self._inputs[child]:
            return
        self._parent[child] = root
        self._inputs[root] |= self._inputs.pop(child)

    def groups(self) -> list[list[Node]]:
        """List the groups, each in node order, by their first node."""
        groups: dict[Node, list[Node]] = {}
        for node in sorted(self._parent):
            groups.setdefault(self.find(node), []).append(node)
        return sorted(groups.values())


def _qualify(entries: Sequence[Mapping[str, Any]]) -> list[list[QualifiedKey]]:
    """Qualify each row's keys by their count in earlier rows."""
    counts: Counter[EntryKey] = Counter()
    qualified = []
    for entry in entries:
        keys = entry_keys(entry)
        qualified.append([(key, counts[key]) for key in keys])
        counts.update(keys)
    return qualified


def _strength(key: EntryKey) -> tuple[int, int]:
    """Rank a key: ids, better ranked databases first, then names, then years."""
    if key[0] == ID_KEY_KIND:
        return (0, _ID_SOURCE_RANKS.get(key[1], len(_ID_SOURCE_RANKS)))
    if key[0] == NAME_YEAR_KEY_KIND:
        return _NAME_YEAR_STRENGTH
    return _NAME_STRENGTH


def _links(holders: Mapping[QualifiedKey, Sequence[Node]]) -> list[_Link]:
    """List every pair of rows sharing a key, strongest first."""
    links: list[_Link] = []
    for (key, _), nodes in holders.items():
        strength = _strength(key)
        links.extend(
            (strength, one, other)
            for index, one in enumerate(nodes)
            for other in nodes[index + 1 :]
        )
    return sorted(links)


class _Grouper:
    """Group the rows of ranked inputs and report what disagreed."""

    def __init__(self, inputs: Sequence[Sequence[Mapping[str, Any]]]) -> None:
        """Qualify every row's keys."""
        self._qualified = [_qualify(entries) for entries in inputs]
        self._conflicts: list[GroupIdConflict] = []

    def _nodes(self) -> Iterator[Node]:
        for input_index, rows in enumerate(self._qualified):
            for row in range(len(rows)):
                yield (input_index, row)

    def _keys(self, node: Node) -> list[QualifiedKey]:
        return self._qualified[node[0]][node[1]]

    def _id_keys(self, node: Node) -> list[QualifiedKey]:
        return [qkey for qkey in self._keys(node) if qkey[0][0] == ID_KEY_KIND]

    def _join(self) -> list[list[Node]]:
        nodes = list(self._nodes())
        holders: dict[QualifiedKey, list[Node]] = {}
        for node in nodes:
            for qkey in self._keys(node):
                holders.setdefault(qkey, []).append(node)
        groups = _Groups(nodes)
        for _, one, other in _links(holders):
            groups.link(one, other)
        return groups.groups()

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
        """Whether some member is in the group by a name key alone, of either kind."""
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
        """Join the rows, then report what the groups disagree on."""
        groups = self._join()
        group_of = {
            node: index for index, members in enumerate(groups) for node in members
        }
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
