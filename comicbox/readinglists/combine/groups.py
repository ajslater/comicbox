"""
Which rows of several lists are the same issue.

Every row is a node ``(input index, row index)`` carrying its
``entry_keys``. A key is qualified by how many earlier rows of its own input
carry it, so the first occurrence of a repeated issue lines up with the
first in another list and the second with the second. The cover-year key
is counted among rows of the same signature (``discriminators``): rows of
two volumes are not repeats of one issue.

Two rows of different inputs that share a qualified key are linked, and
links join groups transitively: a ComicVine id joining A and B and a Metron
id joining B and C put all three together. Links are applied strongest
first, ids in ``ranked_id_sources`` order, then names with a start year or
volume, then names with a cover year, and within one strength by input
rank and row. A link that would put two rows of one input in one group is
refused, so a name match never takes a row an id match wanted, nor a
cover-year match one a name match wanted, and nothing is cut apart
afterwards.

The cover-year key links a row to its candidates: rows of other inputs with
the same key and occurrence whose signatures do not conflict with its own.
An exact candidate has the same signature, a loose one another. Every exact
pair is linked, so a list combines with itself unchanged. A loose pair is
linked only when neither row has an exact candidate in the other's input,
each is the other's only loose candidate there, and neither has two
candidates that conflict over all the other inputs: a row that cannot tell
which volume it is stays its own entry. No group formed through cover-year
links holds two rows whose signatures conflict.
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
    Discriminators,
    EntryKey,
    any_conflict,
    discriminators,
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
_EXACT_STRENGTH = (2, 0)
_LOOSE_STRENGTH = (2, 1)
_COVER_YEAR_STRENGTHS = frozenset({_EXACT_STRENGTH, _LOOSE_STRENGTH})


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
    """
    Disjoint sets of nodes, each holding at most one row per input.

    Each group also knows the discriminators of its rows, so a cover-year
    link can be refused for the whole group, not only the pair it names.
    """

    __slots__ = ("_discriminators", "_inputs", "_parent")

    def __init__(self, values: Mapping[Node, Discriminators]) -> None:
        self._parent: dict[Node, Node] = {node: node for node in values}
        self._inputs: dict[Node, set[int]] = {node: {node[0]} for node in values}
        self._discriminators: dict[Node, frozenset[Discriminators]] = {
            node: frozenset({value}) for node, value in values.items()
        }

    def find(self, node: Node) -> Node:
        """Return the node's root, compressing the path to it."""
        root = node
        while (parent := self._parent[root]) != root:
            root = parent
        while node != root:
            node, self._parent[node] = self._parent[node], root
        return root

    def link(self, one: Node, other: Node, *, guarded: bool = False) -> None:
        """
        Join two nodes' groups, unless both hold a row of one input.

        With ``guarded``, as for a cover-year link, also unless the joined
        group would hold two rows that conflict.
        """
        roots = sorted((self.find(one), self.find(other)))
        root, child = roots
        if root == child or self._inputs[root] & self._inputs[child]:
            return
        values = self._discriminators[root] | self._discriminators[child]
        if guarded and any_conflict(values):
            return
        self._parent[child] = root
        self._inputs[root] |= self._inputs.pop(child)
        self._discriminators[root] = values
        del self._discriminators[child]

    def groups(self) -> list[list[Node]]:
        """List the groups, each in node order, by their first node."""
        groups: dict[Node, list[Node]] = {}
        for node in sorted(self._parent):
            groups.setdefault(self.find(node), []).append(node)
        return sorted(groups.values())


def _qualify(entries: Sequence[Mapping[str, Any]]) -> list[list[QualifiedKey]]:
    """
    Qualify each row's keys by their count in earlier rows.

    The cover-year key is counted among rows of the same signature.
    """
    counts: Counter[tuple[EntryKey, Discriminators | None]] = Counter()
    qualified = []
    for entry in entries:
        value = discriminators(entry)
        tallies = [
            (key, value if key[0] == NAME_YEAR_KEY_KIND else None)
            for key in entry_keys(entry)
        ]
        qualified.append([(tally[0], counts[tally]) for tally in tallies])
        counts.update(tallies)
    return qualified


def _strength(key: EntryKey) -> tuple[int, int]:
    """Rank an id or name key: ids, better ranked databases first, then names."""
    if key[0] == ID_KEY_KIND:
        return (0, _ID_SOURCE_RANKS.get(key[1], len(_ID_SOURCE_RANKS)))
    return _NAME_STRENGTH


class _CoverYear:
    """The rows holding one qualified cover-year key, and their candidates."""

    __slots__ = ("candidates", "values")

    def __init__(
        self, nodes: Sequence[Node], values: Mapping[Node, Discriminators]
    ) -> None:
        self.values = values
        # A row's candidates: rows of other inputs whose signatures do not
        # conflict with its own.
        self.candidates = {
            node: [
                other
                for other in nodes
                if other[0] != node[0] and not values[node].conflicts(values[other])
            ]
            for node in nodes
        }

    def _may_link_loosely(self, one: Node, other: Node) -> bool:
        """
        Tell whether ``one`` lets a loose link to ``other`` be made.

        It has no exact candidate in ``other``'s input, ``other`` is its only
        loose one there, and no two of its candidates conflict.
        """
        there = [node for node in self.candidates[one] if node[0] == other[0]]
        return there == [other] and not any_conflict(
            self.values[node] for node in self.candidates[one]
        )

    def links(self) -> Iterator[_Link]:
        """Yield every exact pair, and the loose pairs both rows allow."""
        for one, others in self.candidates.items():
            for other in others:
                if other <= one:
                    continue
                if self.values[one] == self.values[other]:
                    yield (_EXACT_STRENGTH, one, other)
                elif self._may_link_loosely(one, other) and self._may_link_loosely(
                    other, one
                ):
                    yield (_LOOSE_STRENGTH, one, other)


def _links(
    holders: Mapping[QualifiedKey, Sequence[Node]],
    values: Mapping[Node, Discriminators],
) -> list[_Link]:
    """List every pair of rows to link, strongest first."""
    links: list[_Link] = []
    for (key, _), nodes in holders.items():
        if key[0] == NAME_YEAR_KEY_KIND:
            links.extend(_CoverYear(nodes, values).links())
            continue
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
        """Qualify every row's keys, and note its discriminators."""
        self._qualified = [_qualify(entries) for entries in inputs]
        self._discriminators = {
            (input_index, row): discriminators(entry)
            for input_index, entries in enumerate(inputs)
            for row, entry in enumerate(entries)
        }
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
        groups = _Groups({node: self._discriminators[node] for node in nodes})
        for strength, one, other in _links(holders, self._discriminators):
            groups.link(one, other, guarded=strength in _COVER_YEAR_STRENGTHS)
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
