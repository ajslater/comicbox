"""Transform maps."""

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from bidict import frozenbidict
from glom import Assign, glom

from comicbox.merge import ADD_UNIQUE_MERGER, MERGE_EMPTY_VALUES

DUMMY_PREFIX = "dummy_"


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


@dataclass
class MultiAssigns:
    """Hack for multiple assignments."""

    value: Any
    extra_assigns: tuple[tuple[str, Any], ...]


def _merge_with_old_value(target_dict, dest_path, value):
    if old_value := glom(target_dict, dest_path, default=None):
        ADD_UNIQUE_MERGER.merge(value, old_value)


def _create_extra_assigns(target_dict, value, extra_assigns):
    for extra_dest_path, extra_value in value.extra_assigns:
        _merge_with_old_value(target_dict, extra_dest_path, extra_value)
        if extra_value is not None:
            extra_assign = Assign(extra_dest_path, extra_value, missing=dict)
            extra_assigns.append(extra_assign)
    return value.value


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
        if source_path.startswith(DUMMY_PREFIX):
            value = None
        else:
            value = glom(source_map, source_path, default=None)
            if value in MERGE_EMPTY_VALUES:
                continue
        dest_path, dest_func = dest_spec
        if dest_func:
            value = dest_func(source_map, value)
            if value in MERGE_EMPTY_VALUES:
                continue
        extra_assigns = []
        if isinstance(value, MultiAssigns):
            value = _create_extra_assigns(target_dict, value, extra_assigns)
        _merge_with_old_value(target_dict, dest_path, value)
        assign = Assign(dest_path, value, missing=dict)
        assigns = (assign, *extra_assigns)
        glom(target_dict, assigns)
    return target_dict
