"""
A deep merge function for 🐍.

Modified from https://github.com/clarketm/mergedeep

Vendored under the upstream MIT license:

    Copyright (c) 2019 Travis Clarke

    Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions: The above copyright notice and this
    permission notice shall be included in all copies or substantial
    portions of the Software.
"""

from collections import Counter
from collections.abc import Callable, Mapping, MutableMapping
from copy import deepcopy
from enum import Enum
from functools import partial, reduce
from types import MappingProxyType
from typing import Any


class Strategy(Enum):
    """Merge Strategy Enum."""

    # Replace `dest` item with one from `source` (default).
    REPLACE = 0
    # Combine `list`, `tuple`, `set`, or `Counter` types into one collection.
    ADDITIVE = 1


def _handle_merge_replace(
    dest_parent: MutableMapping[str, Any],
    source_parent: Mapping[str, Any],
    key: str,
) -> None:
    dest = dest_parent[key]
    source = source_parent[key]

    if isinstance(dest, MutableMapping) and isinstance(source, Mapping):
        # Merges Counter as well
        _deepmerge(dest, source, Strategy.REPLACE)
    else:
        # If a key exists in both objects and the values are `different`, the value from
        # the `source` object will be used.
        dest_parent[key] = deepcopy(source)


############
# ADDITIVE #
############


# Each merge func returns the merged collection, which is assigned back to
# the parent: tuples and frozensets are immutable, so merging them in place
# only rebound a local name and the source items were lost.


def _merge_counter(dest: Counter, source: Counter) -> Counter:
    # Update dest if both dest and source are `Counter` type.
    dest.update(deepcopy(source))
    return dest


def _merge_mapping(
    dest: MutableMapping[str, Any],
    source: Mapping[str, Any],
) -> MutableMapping[str, Any]:
    # Recurse on mapping
    return _deepmerge(dest, source, Strategy.ADDITIVE)


def _merge_list(dest: list, source: list | tuple) -> list:
    # Extend dest if both dest and source are `list` type.
    dest.extend(deepcopy(source))
    return dest


def _merge_tuple(dest: tuple, source: list | tuple) -> tuple:
    # Concatenate if dest is a `tuple`.
    return dest + tuple(deepcopy(source))


def _merge_set(dest: set, source: set | frozenset) -> set:
    # Update dest if both dest and source are `set` type.
    dest.update(deepcopy(source))
    return dest


def _merge_frozenset(dest: frozenset, source: set | frozenset) -> frozenset:
    # Union if dest is a `frozenset`.
    return dest | frozenset(deepcopy(source))


_MERGE_MAP: MappingProxyType[tuple, Callable] = MappingProxyType(
    {
        (Counter, Counter): _merge_counter,
        (MutableMapping, Mapping): _merge_mapping,
        (list, list | tuple): _merge_list,
        (tuple, list | tuple): _merge_tuple,
        (set, set | frozenset): _merge_set,
        (frozenset, set | frozenset): _merge_frozenset,
    }
)


def _handle_merge_additive(
    dest_parent: MutableMapping[str, Any],
    source_parent: Mapping[str, Any],
    key: str,
) -> None:
    # Values are combined into one long collection.
    dest = dest_parent[key]
    source = source_parent[key]

    for types, merge_func in _MERGE_MAP.items():
        dest_type, source_type = types
        if isinstance(dest, dest_type) and isinstance(source, source_type):
            dest_parent[key] = merge_func(dest, source)
            break
    else:
        _HANDLE_MERGE[Strategy.REPLACE](dest_parent, source_parent, key)


################
# END ADDITIVE #
################

_HANDLE_MERGE: MappingProxyType[Strategy, Callable] = MappingProxyType(
    {
        Strategy.REPLACE: _handle_merge_replace,
        Strategy.ADDITIVE: _handle_merge_additive,
    }
)


def _deepmerge(
    dest: MutableMapping[str, Any],
    source: Mapping[str, Any],
    strategy: Strategy = Strategy.REPLACE,
) -> MutableMapping[str, Any]:
    for key in source:
        if key in dest:
            if dest[key] is not source[key]:
                # If a key exists in both objects and the values are `same`, the value
                # from the `dest` object will be used.
                _HANDLE_MERGE[strategy](dest, source, key)
        else:
            # If the key exists only in `source`, the value from the `source` object
            # will be used.
            dest[key] = deepcopy(source[key])
    return dest


def merge(
    dest: MutableMapping,
    *sources: Mapping,
    strategy: Strategy = Strategy.REPLACE,
) -> MutableMapping:
    """
    Merge sources into dest according to strategy.

    :param dest: The dest mapping.
    :param sources: The source mappings.
    :param strategy: The merge strategy.
    :return:
    """
    return reduce(partial(_deepmerge, strategy=strategy), sources, dest)
