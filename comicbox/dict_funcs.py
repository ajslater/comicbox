"""Dictionary functions."""

from collections.abc import Mapping
from copy import deepcopy


def case_insensitive_dict(d: dict) -> dict:
    """Make a dict with string keys case insensitive."""
    cid = {k.lower(): (k, v) for k, v in d.items()}
    return {v[0]: v[1] for v in cid.values()}


def deep_update(
    base_dict: dict | None,
    update_dict: Mapping,
    sort=False,  # noqa: FBT002
    case_insensitive=False,  # noqa: FBT002
) -> dict:
    """Deep Dict Update."""
    if base_dict is None:
        base_dict = {}
        if case_insensitive_dict:
            base_dict = case_insensitive_dict(base_dict)
    for key, value in update_dict.items():
        if isinstance(value, dict):
            updated_dict = deep_update(
                base_dict.get(key, value.__class__()),
                value,
                sort=sort,
                case_insensitive=case_insensitive,
            )
            if case_insensitive:
                updated_dict = case_insensitive_dict(updated_dict)
            if sort:
                updated_dict = dict(sorted(updated_dict.items()))
            base_dict[key] = updated_dict
        else:
            base_dict[key] = value
    return base_dict


def move_key_to_dict(key_map, source_dict):
    """Move a value with one key to another dict and mapped key."""
    target_dict = {}
    for tag, key in key_map.items():
        # Tags
        tags = tag.split(".")
        tag_value = deepcopy(source_dict)
        for subtag in tags:
            tag_value = tag_value.get(subtag)
            if tag_value is None:
                break

        if tag_value is None:
            continue

        # Keys
        keys = key.split(".")
        target_value = tag_value
        for subkey in reversed(keys[1:]):
            target_value = {subkey: target_value}
        target_dict[keys[0]] = target_value
    return target_dict


def get_deep(d, key_path, default=None):
    """Get a dot delimited deep key from a dictionary."""
    try:
        level = d
        for subkey in key_path:
            level = level[subkey]
    except KeyError:
        level = default
    return level


def set_deep(d, key_path, value):
    """Set a dot delimited deep key to a dictionary."""
    final_key = key_path[-1]
    key_path = key_path[:-1]
    level = d
    for subkey in key_path:
        level = level[subkey]
    level[final_key] = value


def remove_none_values(data):
    """Recursively removes keys with None values from a Python collection."""
    if isinstance(data, Mapping):
        data_type = type(data)
        data = {
            key: remove_none_values(value)
            for key, value in data.items()
            if value is not None
        }
    elif isinstance(data, list | set | frozenset | tuple):
        data_type = type(data)
        data = data_type(remove_none_values(item) for item in data if item is not None)
    # Return non-iterable values as is
    return data
