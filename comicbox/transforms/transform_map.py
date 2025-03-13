"""Transform maps."""

# TODO move into base
from collections.abc import Callable, Mapping, MutableMapping
from copy import deepcopy
from typing import Any

from glom import assign, delete, glom


def transform_map(
    key_map: Mapping, source_map: Mapping, func: Callable[[Any], Any] | None = None
) -> dict:
    """Move a value with one key to another dict and mapped key."""
    target_dict = {}
    for source_path, dest_path in key_map.items():
        value = glom(source_map, source_path, default=None)
        if value is not None:
            if func:
                value = func(value)
            assign(target_dict, dest_path, deepcopy(value), missing=dict)
    return target_dict


def transform_map_in_place(
    key_map: Mapping,
    transformed_map: MutableMapping,
    func: Callable[[Any], Any] | None = None,
) -> None:
    """Move a value with one key to the same dict and mapped key."""
    for source_path, dest_path in key_map.items():
        value = glom(transformed_map, source_path, default=None)
        delete(transformed_map, source_path, ignore_missing=True)
        if value is not None:
            if func:
                value = func(value)
            assign(transformed_map, dest_path, value, missing=dict)
