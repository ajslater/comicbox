"""Transform maps."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from glom import A, Coalesce, Path, S, T, Val, assign

from comicbox.empty import is_empty
from comicbox.schemas.comicbox import ComicboxSchemaMixin

GLOBAL_SCOPE_PREFIX = "S.globals.comicbox"


@dataclass
class MetaSpec:
    """Define a key mapping and transform functions."""

    key_map: Mapping[str, str | tuple[str, ...]]
    spec: Callable | tuple | None = None
    inherit_root_keypath: bool = True
    assign_global: bool = False


def _path_str_from_tuple(head_keypath: str, tail_keypath: str):
    return ".".join(tuple(filter(bool, (head_keypath, tail_keypath))))


def _path_from_tuple(head_keypath: str, tail_keypath: str):
    path_str = _path_str_from_tuple(head_keypath, tail_keypath)
    return Path.from_text(path_str)


def _get_multi_values_spec(
    source_root_path: Path | None, keypath: str
) -> tuple[str, Coalesce]:
    path_parts = []
    tail_path = Path.from_text(keypath)
    if keypath.startswith(GLOBAL_SCOPE_PREFIX):
        tail_path_parts = tail_path.values()
        path = S.globals.comicbox
        for part in tail_path_parts[3:]:
            path = path[part]
    else:
        if source_root_path:
            path_parts.append(source_root_path)
        path_parts.append(tail_path)
        path = Path(*path_parts)
    # Don't know which of multiple values are critical so don't throw.
    return keypath, Coalesce(path, skip=is_empty, default=None)


def _get_spec_source_values(
    source_root_path_str: str, source_path_strs: tuple[str] | str
):
    if isinstance(source_path_strs, tuple | list):
        source_root_path = (
            Path.from_text(source_root_path_str) if source_root_path_str else None
        )
        values = {}
        for p in source_path_strs:
            key, value = _get_multi_values_spec(source_root_path, p)
            values[key] = value
    else:
        source_path = _path_from_tuple(source_root_path_str, source_path_strs)
        # No default so it throws out of the current spec line.
        values = Coalesce(source_path, skip=is_empty)
    return values


def _get_tail_spec(metaspec_spec):
    tail_spec = metaspec_spec if isinstance(metaspec_spec, tuple) else (metaspec_spec,)
    return filter(bool, tail_spec)


def _get_spec(
    source_head: str,
    source_keypaths: str | tuple[str],
    metaspec: MetaSpec,
    dest_keypath: str,
):
    spec = []
    if values := _get_spec_source_values(source_head, source_keypaths):
        spec.append(values)
    if metaspec.spec:
        tail_spec = _get_tail_spec(metaspec.spec)
        spec.extend(tail_spec)
    if metaspec.assign_global:
        global_assign = (A.globals.comicbox, T[dest_keypath])
        spec.extend(global_assign)

    spec = spec[0] if len(spec) == 1 else tuple(spec)
    # Trap errors to complete the spec
    return Coalesce(spec, default=None)


def _create_spec(
    dest_head: str,
    source_head: str,
    metaspec: MetaSpec,
    dest_keypath: str,
    source_keypaths: str | tuple[str],
):
    full_dest_path = _path_str_from_tuple(dest_head, dest_keypath)
    if not full_dest_path:
        return full_dest_path, ()
    spec = _get_spec(source_head, source_keypaths, metaspec, dest_keypath)
    return full_dest_path, spec


def _create_specs(
    *args,
    dest_root_keypath="",
    source_root_keypath="",
) -> MappingProxyType[str, Any]:
    """Create spec from metaspec map."""
    specs = {}
    for metaspec in args:
        dest_head, source_head = (
            (dest_root_keypath, source_root_keypath)
            if metaspec.inherit_root_keypath and dest_root_keypath
            else ("", "")
        )
        for dest_keypath, source_keypaths in metaspec.key_map.items():
            full_dest_keypath, spec = _create_spec(
                dest_head,
                source_head,
                metaspec,
                dest_keypath,
                source_keypaths,
            )
            if full_dest_keypath and spec:
                # Have to to double assign when assigning actual glom structures
                # They get evaluated or something.
                # But it's in the spec creator so not a huge deal.
                assign(specs, full_dest_keypath, None, missing=dict)
                assign(specs, full_dest_keypath, Val(spec), missing=dict)
    return MappingProxyType(specs)


def create_specs_to_comicbox(
    *metaspecs,
    format_root_keypath: str = "",
    comicbox_root_keypath=ComicboxSchemaMixin.ROOT_KEYPATH,
):
    """Create to comicbox specs."""
    return _create_specs(
        *metaspecs,
        dest_root_keypath=comicbox_root_keypath,
        source_root_keypath=format_root_keypath,
    )


def create_specs_from_comicbox(
    *metaspecs,
    format_root_keypath: str = "",
    comicbox_root_keypath=ComicboxSchemaMixin.ROOT_KEYPATH,
):
    """Create from comicbox specs."""
    return _create_specs(
        *metaspecs,
        dest_root_keypath=format_root_keypath,
        source_root_keypath=comicbox_root_keypath,
    )
