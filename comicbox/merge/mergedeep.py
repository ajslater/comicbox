"""
A deep merge function for 🐍.

Modified from https://github.com/clarketm/mergedeep
"""

from collections import Counter
from collections.abc import Callable, Mapping, MutableMapping
from copy import deepcopy
from enum import Enum
from functools import partial, reduce
from types import MappingProxyType


class Strategy(Enum):
    """Merge Strategy Enum."""

    # Replace `dest` item with one from `source` (default).
    REPLACE = 0
    # Combine `list`, `tuple`, `set`, or `Counter` types into one collection.
    ADDITIVE = 1


def _handle_merge_replace(dest_parent, source_parent, key):
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


def _merge_counter(dest, source):
    # Update dest if both dest and source are `Counter` type.
    dest.update(deepcopy(source))


def _merge_mapping(dest, source):
    # Recurse on mapping
    _deepmerge(dest, source, Strategy.ADDITIVE)


def _merge_list(dest, source):
    # Extend dest if both dest and source are `list` type.
    dest.extend(deepcopy(source))


def _merge_tuple(dest, source):
    # Update dest if both dest and source are `tuple` type.
    dest += tuple(deepcopy(source))


def _merge_set(dest, source):
    # Update dest if both dest and source are `set` type.
    dest.update(deepcopy(source))


_MERGE_MAP: MappingProxyType[tuple, Callable] = MappingProxyType(
    {
        (Counter, Counter): _merge_counter,
        (MutableMapping, Mapping): _merge_mapping,
        (list, list | tuple): _merge_list,
        (tuple, list | tuple): _merge_tuple,
        (set, set | frozenset): _merge_set,
    }
)


def _handle_merge_additive(dest_parent, source_parent, key):
    # Values are combined into one long collection.
    dest = dest_parent[key]
    source = source_parent[key]

    for types, merge_func in _MERGE_MAP.items():
        dest_type, source_type = types
        if isinstance(dest, dest_type) and isinstance(source, source_type):
            merge_func(dest, source)
            break
    else:
        _HANDLE_MERGE[Strategy.REPLACE](dest_parent, source_parent, key)


################
# END ADDITIVE #
################

_HANDLE_MERGE = {
    Strategy.REPLACE: _handle_merge_replace,
    Strategy.ADDITIVE: _handle_merge_additive,
}


def _deepmerge(dest, source, strategy=Strategy.REPLACE):
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
