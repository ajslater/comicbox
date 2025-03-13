"""Dictionary functions."""

from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import Any


def get_deep(d: Mapping, key_path: tuple | list, default=None) -> Any:
    """Get a dot delimited deep key from a dictionary."""
    try:
        level = d
        for subkey in key_path:
            level = level[subkey]
    except KeyError:
        level = default
    return level

def set_deep(d: MutableMapping, key_path: tuple | list, value) -> None:
    """Set a dot delimited deep key to a dictionary."""
    final_key = key_path[-1]
    level = d
    for subkey in key_path[:-1]:
        if subkey not in level:
            level[subkey] = {}
        level = level[subkey]
    level[final_key] = value


def transform_map(key_map: Mapping, source_map: Mapping) -> dict:
    """Move a value with one key to another dict and mapped key."""
    target_dict = {}
    for source_path, dest_path in key_map.items():
        value = get_deep(source_map, source_path)
        if value is None:
            continue
        set_deep(target_dict, dest_path, deepcopy(value))
    return target_dict
