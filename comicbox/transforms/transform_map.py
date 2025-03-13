"""Transform maps."""

# TODO move into base
from collections.abc import Mapping, MutableMapping
from copy import deepcopy

from glom import Assign, Delete, glom


def transform_map(
    spec_map: Mapping,
    source_map: Mapping,
    in_place: bool = False,  # noqa: FBT002
) -> MutableMapping:
    """Move a value with one key to another dict and mapped key."""
    target_dict: MutableMapping = source_map if in_place else {}  # type: ignore[reportAssignmentType]
    for (
        source_spec,
        dest_spec,
    ) in spec_map.items():
        source_path, _ = source_spec
        value = glom(source_map, source_path, default=None)
        if in_place:
            delete = Delete(source_path, ignore_missing=True)
            glom(target_dict, delete)
        if value is not None:
            dest_path, dest_func = dest_spec
            if not in_place:
                value = deepcopy(value)
            if dest_func:
                value = dest_func(value)
            assign = Assign(dest_path, value, missing=dict)
            glom(target_dict, assign)
    return target_dict
