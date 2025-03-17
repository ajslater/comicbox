"""Transform maps."""

from collections.abc import Callable, Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass

from bidict import frozenbidict
from glom import Assign, glom

from comicbox.merge import ADD_UNIQUE_MERGER


@dataclass
class KeyTransforms:
    """Define a key mapping and transform functions."""

    key_map: Mapping
    to_cb: Callable | None = None
    from_cb: Callable | None = None


def create_transform_map(*args) -> frozenbidict:
    """Create the transform map."""
    tm = {}
    for kts in args:
        for format_key, comicbox_key in kts.key_map.items():
            tm[(format_key, kts.from_cb)] = (
                comicbox_key,
                kts.to_cb,
            )
    return frozenbidict(tm)


def transform_map(
    spec_map: Mapping,
    source_map: Mapping,
) -> MutableMapping:
    """Move a value with one key to another dict and mapped key."""
    target_dict = {}
    for (
        source_spec,
        dest_spec,
    ) in spec_map.items():
        source_path, _ = source_spec
        value = glom(source_map, source_path, default=None)
        if value is not None:
            dest_path, dest_func = dest_spec
            value = deepcopy(value)
            if dest_func:
                value = dest_func(value)
            if old_value := glom(target_dict, dest_path, default=None):
                ADD_UNIQUE_MERGER.merge(value, old_value)
            assign = Assign(dest_path, value, missing=dict)
            glom(target_dict, assign)
    return target_dict
