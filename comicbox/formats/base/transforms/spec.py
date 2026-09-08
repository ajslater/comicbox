"""
Transform maps.

A `MetaSpec` maps destination keypaths to source keypaths. `_create_specs`
compiles a set of them into one glom spec in two phases, and refuses to compile
a set whose declarations contradict each other.

Destination keyspace: a compile owns its destinations. Two metaspecs claiming
the same keypath, or one claiming a keypath nested inside another's, raise at
import. glom's `assign` used to resolve those silently -- the later mapping won
the value at the earlier one's slot, and a nested pair either lost the whole
subtree or was set as an *attribute* of the enclosing spec and never reached the
output.

Scope channel: a metaspec with `assign_global` publishes its spec function's
result into glom's per call globals, and other metaspecs read it back by naming
`S.globals.comicbox.<key>` among their sources. glom evaluates a compiled dict
in key insertion order, so phase one compiles the producers and phase two
everything else. Declaration order no longer decides whether a read resolves.
Only one producer per compile: a second publish replaces the whole scope
mapping. Readers still supply their own default, because publishing happens at
runtime over data that may hold nothing; the compile only proves a producer
exists.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, NoReturn

from glom import SKIP, A, Coalesce, Path, S, T, Val, assign

from comicbox.constants import ROOT_KEYPATH
from comicbox.empty import is_empty

GLOBAL_SCOPE_PREFIX = "S.globals.comicbox"
_GLOBAL_SCOPE_PREFIX_PARTS = 3


@dataclass
class MetaSpec:
    """Define a key mapping and transform functions."""

    key_map: Mapping[str, str | tuple[str, ...]]
    spec: Callable | tuple | None = None
    inherit_root_keypath: bool = True
    # Publish this mapping's result on the scope channel. See the module docstring.
    assign_global: bool = False


_IndexedMetaSpec = tuple[int, MetaSpec]


def _metaspec_label(index: int) -> str:
    return f"metaspec[{index}]"


def _roots_label(dest_root_keypath: str, source_root_keypath: str) -> str:
    """Name the compile a declaration error came from."""
    source = source_root_keypath or "(root)"
    dest = dest_root_keypath or "(root)"
    return f"{source} -> {dest}"


class _ScopeChannel:
    """The scope channel one compile declares."""

    def __init__(self, roots_label: str) -> None:
        """Start an empty channel for one compile."""
        self._roots_label = roots_label
        self._published: list[tuple[int, str]] = []
        self._reads: list[tuple[int, str]] = []

    def _raise(self, detail: str) -> NoReturn:
        reason = f"MetaSpec scope error compiling {self._roots_label}: {detail}"
        raise RuntimeError(reason)

    def _read_tails(
        self, index: int, source_keypaths: str | tuple[str, ...]
    ) -> tuple[str, ...]:
        """Return the scope keys one key map entry reads."""
        if not isinstance(source_keypaths, tuple | list):
            if source_keypaths.startswith(GLOBAL_SCOPE_PREFIX):
                self._raise(
                    f"{_metaspec_label(index)} reads {source_keypaths!r} as its only"
                    " source. Only a tuple of sources reads the scope. A lone one"
                    " compiles to a data path under the source root and never matches."
                )
            return ()
        return tuple(
            ".".join(Path.from_text(keypath).values()[_GLOBAL_SCOPE_PREFIX_PARTS:])
            for keypath in source_keypaths
            if keypath.startswith(GLOBAL_SCOPE_PREFIX)
        )

    def _add_producer(
        self, index: int, metaspec: MetaSpec, reads: tuple[str, ...]
    ) -> None:
        if reads:
            self._raise(
                f"{_metaspec_label(index)} publishes to the scope and also reads"
                f" {reads[0]!r} from it, but its read is evaluated first."
            )
        for dest in metaspec.key_map:
            if "." in dest:
                self._raise(
                    f"{_metaspec_label(index)} publishes the dotted destination"
                    f" {dest!r}. A producer publishes under one literal key while"
                    " readers descend the path a part at a time, so no read could"
                    " ever match it."
                )
            self._published.append((index, dest))

    def add(self, index: int, metaspec: MetaSpec) -> None:
        """Record what one metaspec publishes to and reads from the scope."""
        reads = tuple(
            tail
            for source_keypaths in metaspec.key_map.values()
            for tail in self._read_tails(index, source_keypaths)
        )
        if metaspec.assign_global:
            self._add_producer(index, metaspec, reads)
        self._reads.extend((index, tail) for tail in reads)

    def validate(self) -> None:
        """Check that one producer publishes every key that is read."""
        if len(self._published) > 1:
            publishers = ", ".join(
                f"{_metaspec_label(index)} -> {dest!r}"
                for index, dest in self._published
            )
            self._raise(
                "only one destination may publish to the scope, because a second"
                f" publish replaces the whole scope mapping, but {publishers} do."
            )
        published_keys = {dest for _, dest in self._published}
        for index, tail in self._reads:
            if tail not in published_keys:
                self._raise(
                    f"{_metaspec_label(index)} reads {GLOBAL_SCOPE_PREFIX}.{tail} but"
                    " no metaspec in this compile publishes it, so the read would"
                    " silently fall back to the spec function's own default."
                )


def _validate_scope_channel(
    indexed_metaspecs: tuple[_IndexedMetaSpec, ...], roots_label: str
) -> None:
    """Refuse to compile a scope channel that cannot resolve."""
    channel = _ScopeChannel(roots_label)
    for index, metaspec in indexed_metaspecs:
        channel.add(index, metaspec)
    channel.validate()


def _partition_metaspecs(
    indexed_metaspecs: tuple[_IndexedMetaSpec, ...],
) -> tuple[_IndexedMetaSpec, ...]:
    """Order scope producers ahead of everything that might read them."""
    producers = tuple(pair for pair in indexed_metaspecs if pair[1].assign_global)
    consumers = tuple(pair for pair in indexed_metaspecs if not pair[1].assign_global)
    return producers + consumers


def _dest_prefixes(keypath: str) -> tuple[str, ...]:
    """Return every keypath a destination nests inside."""
    parts = keypath.split(".")
    return tuple(".".join(parts[:index]) for index in range(1, len(parts)))


class _DestKeyspace:
    """The destination keypaths one compile has claimed."""

    def __init__(self, roots_label: str) -> None:
        """Start an empty keyspace for one compile."""
        self._roots_label = roots_label
        self._leaves: dict[str, str] = {}
        self._branches: dict[str, str] = {}

    def _find_conflict(self, keypath: str) -> tuple[str, str] | None:
        """Return the claimed keypath this one collides with, and how."""
        if keypath in self._leaves:
            return keypath, "is already claimed by"
        if enclosed := self._branches.get(keypath):
            return enclosed, "encloses"
        for prefix in _dest_prefixes(keypath):
            if prefix in self._leaves:
                return prefix, "nests inside"
        return None

    def claim(self, keypath: str, claimant: str) -> None:
        """Record a destination, refusing one that collides with an earlier one."""
        if conflict := self._find_conflict(keypath):
            other_keypath, relation = conflict
            reason = (
                f"MetaSpec destination collision compiling {self._roots_label}:"
                f" {claimant} -> {keypath!r} {relation} {other_keypath!r} from"
                f" {self._leaves[other_keypath]}. One of them would be silently"
                " discarded. Give them distinct destinations."
            )
            raise RuntimeError(reason)
        self._leaves[keypath] = claimant
        for prefix in _dest_prefixes(keypath):
            self._branches.setdefault(prefix, keypath)


def _path_str_from_tuple(head_keypath: str, tail_keypath: str) -> str:
    return ".".join(tuple(filter(bool, (head_keypath, tail_keypath))))


def _path_from_tuple(head_keypath: str, tail_keypath: str) -> Path:
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
        for part in tail_path_parts[_GLOBAL_SCOPE_PREFIX_PARTS:]:
            path = path[part]
    else:
        if source_root_path:
            path_parts.append(source_root_path)
        path_parts.append(tail_path)
        path = Path(*path_parts)
    # Don't know which of multiple values are critical so don't throw.
    # SKIP, not None: a missing source must leave the key *out* of the values
    # dict. Emitting an explicit None made every `values.get(key, default)` in
    # the spec functions return None instead of the default they asked for.
    return keypath, Coalesce(path, skip=is_empty, default=SKIP)


def _get_spec_source_values(
    source_root_path_str: str, source_path_strs: tuple[str, ...] | str
) -> dict | Coalesce:
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


def _get_tail_spec(
    metaspec_spec: Any,
) -> filter:
    tail_spec = metaspec_spec if isinstance(metaspec_spec, tuple) else (metaspec_spec,)
    return filter(bool, tail_spec)


def _get_spec(
    source_head: str,
    source_keypaths: str | tuple[str, ...],
    metaspec: MetaSpec,
    dest_keypath: str,
) -> Coalesce:
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
    source_keypaths: str | tuple[str, ...],
) -> tuple[str, Coalesce] | tuple[str, tuple]:
    full_dest_path = _path_str_from_tuple(dest_head, dest_keypath)
    if not full_dest_path:
        return full_dest_path, ()
    spec = _get_spec(source_head, source_keypaths, metaspec, dest_keypath)
    return full_dest_path, spec


def _create_specs(
    *args: MetaSpec,
    dest_root_keypath: str = "",
    source_root_keypath: str = "",
) -> MappingProxyType[str, Any]:
    """Create spec from metaspec map."""
    roots_label = _roots_label(dest_root_keypath, source_root_keypath)
    indexed_metaspecs = tuple(enumerate(args))
    _validate_scope_channel(indexed_metaspecs, roots_label)
    keyspace = _DestKeyspace(roots_label)
    specs = {}
    for index, metaspec in _partition_metaspecs(indexed_metaspecs):
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
                claimant = f"{_metaspec_label(index)} key_map[{dest_keypath!r}]"
                keyspace.claim(full_dest_keypath, claimant)
                # Have to to double assign when assigning actual glom structures
                # They get evaluated or something.
                # But it's in the spec creator so not a huge deal.
                assign(specs, full_dest_keypath, None, missing=dict)
                assign(specs, full_dest_keypath, Val(spec), missing=dict)
    return MappingProxyType(specs)


def create_specs_to_comicbox(
    *metaspecs: MetaSpec,
    format_root_keypath: str = "",
    comicbox_root_keypath: str = ROOT_KEYPATH,
) -> MappingProxyType[str, dict[str, Coalesce] | Coalesce]:
    """Create to comicbox specs."""
    return _create_specs(
        *metaspecs,
        dest_root_keypath=comicbox_root_keypath,
        source_root_keypath=format_root_keypath,
    )


def create_specs_from_comicbox(
    *metaspecs: MetaSpec,
    format_root_keypath: str = "",
    comicbox_root_keypath: str = ROOT_KEYPATH,
) -> MappingProxyType[
    str, dict[str, dict[str, Coalesce]] | dict[str, Coalesce] | Coalesce
]:
    """Create from comicbox specs."""
    return _create_specs(
        *metaspecs,
        dest_root_keypath=format_root_keypath,
        source_root_keypath=comicbox_root_keypath,
    )
