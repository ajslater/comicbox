"""Transform maps."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bidict import frozenbidict
from glom import Assign, Path, glom

from comicbox.merge import ADD_UNIQUE_MERGER, MERGE_EMPTY_VALUES
from comicbox.schemas.comicbox_mixin import ComicboxSchemaMixin

DUMMY_PREFIX = "dummy_"


@dataclass
class KeyTransforms:
    """Define a key mapping and transform functions."""

    key_map: Mapping
    to_cb: Callable | None = None
    from_cb: Callable | None = None


def create_transform_map(
    *args,
    format_root_key_path_path="",
    comicbox_root_key=ComicboxSchemaMixin.ROOT_TAG,
    # XXX only_comicbox_root_tag probably a hack.
    only_comicbox_root_tag=True,
) -> frozenbidict[tuple[str, str, Callable | None], tuple[str, str, Callable | None]]:
    """Create the transform map."""
    tm = {}
    for kts in args:
        for format_key, comicbox_key in kts.key_map.items():
            if format_root_key_path_path:
                full_format_key = (format_root_key_path_path, format_key)
            else:
                full_format_key = ("", format_key)
            if format_root_key_path_path or only_comicbox_root_tag:
                full_comicbox_key = (comicbox_root_key, comicbox_key)
            else:
                full_comicbox_key = ("", comicbox_key)
            tm[(full_format_key, kts.from_cb)] = (
                full_comicbox_key,
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


def _create_extra_assigns(target_dict, value, extra_assigns, dest_root_path_str):
    for extra_dest_path, extra_value in value.extra_assigns:
        parsed_extra_dest_path = _path_from_tuple((dest_root_path_str, extra_dest_path))
        _merge_with_old_value(target_dict, parsed_extra_dest_path, extra_value)
        if extra_value is not None:
            extra_assign = Assign(parsed_extra_dest_path, extra_value, missing=dict)
            extra_assigns.append(extra_assign)
    return value.value


def _path_from_tuple(path_tuple):
    head, tail = path_tuple
    parts = []
    if head:
        parts.append(Path.from_text(head))
    if tail:
        parts.append(Path.from_text(tail))
    return Path(*parts)


def transform_map(
    spec_map: Mapping,
    source_map: Mapping,
    in_place: bool = False,  # noqa: FBT002
) -> dict:
    """Move a value with one key to another dict and mapped key."""
    source_map = dict(source_map)
    if not spec_map:
        return source_map
    target_dict = source_map if in_place else {}
    for (
        source_spec,
        dest_spec,
    ) in spec_map.items():
        source_path_tuple, _ = source_spec
        _, source_path_str = source_path_tuple
        if source_path_str.startswith(DUMMY_PREFIX):
            value = None
        else:
            source_path = _path_from_tuple(source_path_tuple)
            value = glom(source_map, source_path, default=None)
            if value in MERGE_EMPTY_VALUES:
                continue
        dest_path_tuple, dest_func = dest_spec
        if dest_func:
            value = dest_func(source_map, value)
            if value in MERGE_EMPTY_VALUES:
                continue
        extra_assigns = []
        if isinstance(value, MultiAssigns):
            dest_root_path_str, _ = dest_path_tuple
            value = _create_extra_assigns(
                target_dict, value, extra_assigns, dest_root_path_str
            )
        assigns = []
        dest_path = _path_from_tuple(dest_path_tuple)
        if not dest_path.startswith(DUMMY_PREFIX):
            _merge_with_old_value(target_dict, dest_path, value)
            assign = Assign(dest_path, value, missing=dict)
            assigns.append(assign)
        assigns.extend(extra_assigns)
        assigns = tuple(assigns)
        glom(target_dict, assigns)
    return target_dict
