"""Dictionary functions."""

from copy import deepcopy


def move_key_to_dict(key_map, source_dict):
    """Move a value with one key to another dict and mapped key."""
    # TODO look at generic deep map libs
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
