"""Dictionary functions."""

from collections.abc import Mapping


def sort_dict(d):
    """Recursively sort a Mapping type."""
    result = {}
    for k, v in sorted(d.items()):
        if isinstance(v, Mapping):
            result[k] = sort_dict(v)
        else:
            result[k] = v
    return result


def deep_update(base_dict, update_dict):
    """Deep Dict Update."""
    for key, value in update_dict.items():
        if isinstance(value, Mapping):
            base_dict[key] = deep_update(base_dict.get(key, {}), value)
        else:
            base_dict[key] = value
    return base_dict
