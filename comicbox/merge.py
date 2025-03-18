"""Dictionary functions."""

# All this just because I want to remove empties during the merge and not after.
# Otherwise I could do all of this with the simpler mergedeep package.
from collections.abc import Mapping, MutableMapping
from contextlib import suppress
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


class RecursiveExtendedSet(ExtendedSet):
    """DeepDiff's extended set but recursive for collections."""

    def _hash_element(self, element: Any) -> int:
        with suppress(TypeError):
            return hash(element)
        if isinstance(element, dict):
            sorted_keys = sorted(element.keys())
            hash_str = ",".join(
                [
                    f"{self._hash_element(key)}:{self._hash_element(element[key])}"
                    for key in sorted_keys
                ]
            )
        elif isinstance(element, list | tuple | set | frozenset):
            sorted_keys = sorted(element)
            hash_str = ",".join([f"{self._hash_element(key)}" for key in sorted_keys])
        else:
            hash_str = str(element)
        return hash(hash_str)

    def __repr__(self):
        """Represent as a string."""
        return str(self._values_by_hash.values())


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


def coerce_mapping_to_dict(value):
    """Coerce mappings to dicts, because ruamel.yaml returns it's own commented mapping type."""
    return dict(value) if isinstance(value, Mapping) else value


class RemoveEmptyMappingStrategies(DictStrategies):
    """Dict strategies that remove empties."""

    @staticmethod
    def strategy_merge_skip_empty(
        config: Merger,
        path: list,
        base: MutableMapping,
        nxt: Mapping,
        override=False,  # noqa: FBT002
    ) -> MutableMapping:
        """Update keys or if they exist, merge them by type, but ignore empty values in nxt."""
        for k, v in nxt.items():
            if v in MERGE_EMPTY_VALUES:
                continue
            new_v = (
                v
                if override or k not in base
                else config.value_strategy([*path, k], base[k], v)
            )
            base[k] = coerce_mapping_to_dict(new_v)

        return base

    @classmethod
    def strategy_override_skip_empty(
        cls,
        config: Merger,
        path: list,
        base: MutableMapping,
        nxt: Mapping,
    ) -> Any:
        """Update keys, delete any None entries in nxt in base, and ignore other empty values in nxt."""
        cls.strategy_merge_skip_empty(config, path, base, nxt, override=True)


class RemoveEmptyListStrategies(
    RemoveEmptyOverrideSimpleStrategiesMixin, ListStrategies
):
    """List strategies that remove empties."""

    @staticmethod
    def unique_nxt(base, nxt, unique):
        """Optionally make nxt only the values new to base."""
        if not unique:
            return nxt
        base_as_set = RecursiveExtendedSet(base)
        return tuple(e for e in nxt if e not in base_as_set)

    @classmethod
    def strategy_append_skip_empty(
        cls,
        config: Merger,
        path: list,
        base: list | tuple,
        nxt: list | tuple,
    ) -> list | tuple:
        """Append nxt to base, but ignore empty values in nxt."""
        return cls.strategy_append_unique_skip_empty(
            config, path, base, nxt, unique=False
        )

    @classmethod
    def strategy_append_unique_skip_empty(
        cls,
        config: Merger,  # noqa: ARG003
        path: list,  # noqa: ARG003
        base: list | tuple,
        nxt: list | tuple,
        unique: bool = True,  # noqa: FBT002
    ) -> list | tuple:
        """Append items without duplicates in nxt to base, but ignore empty values in nxt."""
        if nxt := tuple(filter(lambda e: e not in EMPTY_VALUES, nxt)) and (
            nxt := cls.unique_nxt(base, nxt, unique)
        ):
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


class RemoveEmptyFallbackStrategies(
    RemoveEmptyFallbackStrategiesMixin, FallbackStrategies
):
    """Fallback strategies that removes empties."""


class RemoveEmptyTypeConflictStrategies(
    RemoveEmptyFallbackStrategiesMixin, TypeConflictStrategies
):
    """Type Conflict strategies that removes empties."""


_ADDITIVE_MERGE_STRATEGIES: list[tuple[type, StrategyCallable]] = [
    (Mapping, RemoveEmptyMappingStrategies.strategy_merge_skip_empty),
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
    (Mapping, RemoveEmptyMappingStrategies.strategy_override_skip_empty),
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
