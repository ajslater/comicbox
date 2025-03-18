"""Dictionary functions."""

# All this just because I want to remove empties during the merge and not after.
# Otherwise I could do all of this with the simpler mergedeep package.
from collections.abc import Mapping, MutableMapping
from typing import Any

from deepmerge.extended_set import ExtendedSet
from deepmerge.merger import Merger
from deepmerge.strategy.core import StrategyCallable
from deepmerge.strategy.dict import DictStrategies
from deepmerge.strategy.fallback import FallbackStrategies
from deepmerge.strategy.list import ListStrategies
from deepmerge.strategy.set import SetStrategies
from deepmerge.strategy.type_conflict import TypeConflictStrategies

# Ordered by expected frequency, excludes dict
MERGE_EMPTY_VALUES = ("", [], set(), None, frozenset(), ())
EMPTY_VALUES = (*MERGE_EMPTY_VALUES, {})


class RemoveEmptyOverrideSimpleStrategiesMixin:
    """Remove empties from any simple non mapping container."""

    @staticmethod
    def strategy_override_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: list | set,
        nxt: Any,
    ) -> Any:
        """Update keys, but ignore empty values in nxt."""
        return base if nxt else nxt

    @staticmethod
    def strategy_pop_none(
        config: Merger,
        path: list,
        base: list | set,
        nxt: Any,
    ) -> Any:
        """Pop nones from all dict members of sequences."""
        new_base = []
        for index, base_e in enumerate(base):
            for nxt_e in nxt:
                new_e = config.value_strategy([*path, index], base_e, nxt_e)
                if new_e:
                    new_base.append(new_e)
        return type(base)(new_base)


def coerce_mapping_to_dict(value):
    """Coerce mappings to dicts, because ruamel.yaml returns it's own commented mapping type."""
    return dict(value) if isinstance(value, Mapping) else value


class RemoveEmptyDictStrategies(DictStrategies):
    """Dict strategies that remove empties."""

    @staticmethod
    def strategy_merge_skip_empty(
        config: Merger, path: list, base: MutableMapping, nxt: Mapping
    ) -> MutableMapping:
        """Update keys or if they exist, merge them by type, but ignore empty values in nxt."""
        for k, v in nxt.items():
            if v in MERGE_EMPTY_VALUES:
                continue
            new_v = (
                v if k not in base else config.value_strategy([*path, k], base[k], v)
            )
            base[k] = coerce_mapping_to_dict(new_v)

        return base

    @staticmethod
    def strategy_override_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: MutableMapping,
        nxt: Mapping,
    ) -> Any:
        """Update keys, delete any None entries in nxt in base, and ignore other empty values in nxt."""
        for k, v in nxt.items():
            if v in MERGE_EMPTY_VALUES:
                continue
            base[k] = coerce_mapping_to_dict(v)

    @staticmethod
    def strategy_pop_none(
        config: Merger,
        path: list,
        base: MutableMapping,
        nxt: Mapping,
    ):
        """Pop none from dicts."""
        for k, v in nxt.items():
            if v is None:
                base.pop(k, None)
            else:
                base[k] = config.value_strategy([*path, k], base[k], v)
        return base


class RemoveEmptyListStrategies(
    RemoveEmptyOverrideSimpleStrategiesMixin, ListStrategies
):
    """List strategies that remove empties."""

    @staticmethod
    def strategy_append_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: list | tuple,
        nxt: list | tuple,
    ) -> list | tuple:
        """Append nxt to base, but ignore empty values in nxt."""
        if nxt := tuple(filter(lambda e: e not in EMPTY_VALUES, nxt)):
            if isinstance(base, tuple):
                base = base + tuple(nxt)
            else:
                base.extend(nxt)
        return base

    @staticmethod
    def strategy_append_unique_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: list | tuple,
        nxt: list | tuple,
    ) -> list | tuple:
        """Append items without duplicates in nxt to base, but ignore empty values in nxt."""
        if nxt := tuple(filter(lambda e: e not in EMPTY_VALUES, nxt)):
            base_as_set = ExtendedSet(base)
            if nxt := tuple(filter(lambda e: e not in base_as_set, nxt)):
                if isinstance(base, tuple):
                    base = base + nxt
                else:
                    base.extend(nxt)
        return base


class RemoveEmptySetStrategies(RemoveEmptyOverrideSimpleStrategiesMixin, SetStrategies):
    """Set strategies that remove empties."""

    @staticmethod
    def strategy_union_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: set | frozenset,
        nxt: set | frozenset,
    ) -> set | frozenset:
        """Merge items without duplicates in nxt to base, but ignore empty values in nxt."""
        nxt = frozenset(filter(lambda e: e not in EMPTY_VALUES, nxt))
        return type(base)(base | nxt)


class RemoveEmptyFallbackStrategiesMixin:
    """Remove Empty fallback and type conflict strategies."""

    @staticmethod
    def strategy_override_skip_empty(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: Any,
        nxt: Any,
    ) -> Any:
        """Use nxt, ignore base, but strip of empty values."""
        if isinstance(nxt, Mapping):
            return {k: v for k, v in nxt.items() if v not in MERGE_EMPTY_VALUES}
        if isinstance(nxt, list | tuple | set | frozenset):
            return type(nxt)(filter(lambda e: e not in EMPTY_VALUES, nxt))
        if nxt not in MERGE_EMPTY_VALUES:
            return nxt
        return base

    @staticmethod
    def strategy_pop_none(
        config: Merger,  # noqa: ARG004
        path: list,  # noqa: ARG004
        base: Any,  # noqa: ARG004
        nxt: Any,  # noqa: ARG004
    ) -> Any:
        """Use nxt, ignore base, but strip of empty values."""
        return None


class RemoveEmptyFallbackStrategies(
    RemoveEmptyFallbackStrategiesMixin, FallbackStrategies
):
    """Fallback strategies that removes empties."""


class RemoveEmptyTypeConflictStrategies(
    RemoveEmptyFallbackStrategiesMixin, TypeConflictStrategies
):
    """Type Conflict strategies that removes empties."""


_ADDITIVE_MERGE_STRATEGIES: list[tuple[type, StrategyCallable]] = [
    (Mapping, RemoveEmptyDictStrategies.strategy_merge_skip_empty),
    (list, RemoveEmptyListStrategies.strategy_append_unique_skip_empty),
    (tuple, RemoveEmptyListStrategies.strategy_append_unique_skip_empty),
    (set, RemoveEmptySetStrategies.strategy_union_skip_empty),
    (frozenset, RemoveEmptySetStrategies.strategy_union_skip_empty),
]
ADD_UNIQUE_MERGER: Merger = Merger(
    _ADDITIVE_MERGE_STRATEGIES,
    [RemoveEmptyFallbackStrategies.strategy_override_skip_empty],
    [RemoveEmptyTypeConflictStrategies.strategy_override_skip_empty],
)

_REPLACE_MERGE_STRATEGIES: list[tuple[type, StrategyCallable]] = [
    (Mapping, RemoveEmptyDictStrategies.strategy_override_skip_empty),
    (list, RemoveEmptyListStrategies.strategy_override_skip_empty),
    (tuple, RemoveEmptyListStrategies.strategy_override_skip_empty),
    (set, RemoveEmptySetStrategies.strategy_override_skip_empty),
    (frozenset, RemoveEmptySetStrategies.strategy_override_skip_empty),
]
REPLACE_MERGER: Merger = Merger(
    _REPLACE_MERGE_STRATEGIES,
    [RemoveEmptyFallbackStrategies.strategy_override_skip_empty],
    [RemoveEmptyTypeConflictStrategies.strategy_override_skip_empty],
)

_POP_NONE_MERGE_STRATEGIES: list[tuple[type, StrategyCallable]] = [
    (Mapping, RemoveEmptyDictStrategies.strategy_pop_none),
    (list, RemoveEmptyListStrategies.strategy_pop_none),
    (tuple, RemoveEmptyListStrategies.strategy_pop_none),
    (set, RemoveEmptySetStrategies.strategy_pop_none),
    (frozenset, RemoveEmptySetStrategies.strategy_pop_none),
]

POP_NONE_MERGER: Merger = Merger(
    _POP_NONE_MERGE_STRATEGIES,
    [RemoveEmptyFallbackStrategies.strategy_pop_none],
    [RemoveEmptyTypeConflictStrategies.strategy_pop_none],
)
