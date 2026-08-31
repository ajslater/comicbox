"""
Typed runtime config for comicbox.

Built once by ``get_config()`` from the validated confuse AttrDict; every
downstream module takes ``ComicboxSettings`` instead of ``AttrDict``.

The dataclass tree mirrors the YAML config tree and the CLI argument
groups one-for-one:

    comicbox:
      general / read / write / print / convert / compute
      online:
        lookup / auth / cache / tuning

This taxonomy is the source of truth for the config tree. New options
must land under the group that owns their concern.

The ``online`` subtree is big enough to live in its own package —
``comicbox.config.online.settings``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    # comicbox.config.online.settings imports parse_enum from here at
    # runtime, so the reference back stays type-only.
    from comicbox.config.online.settings import OnlineSettings
    from comicbox.formats import MetadataFormats
    from comicbox.formats.sources import MetadataSources
    from comicbox.print import PrintPhases

_EnumT = TypeVar("_EnumT", bound=Enum)


def parse_enum(
    enum_cls: type[_EnumT], flag: str, raw: str, *, noun: str = "name"
) -> _EnumT:
    """Parse a lowercased string into an enum member, raising a flag-tagged error."""
    try:
        return enum_cls(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(member.value for member in enum_cls)
        reason = f"{flag}: unknown {noun} {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


@dataclass(frozen=True, slots=True)
class GeneralSettings:
    """Cross-cutting options that don't fit a verb-specific group."""

    config: str | Path | None = None
    recurse: bool = False
    dry_run: bool = False
    loglevel: str | int = "INFO"
    dest_path: str | Path = "."
    delete_keys: frozenset[str] = field(default_factory=frozenset)
    delete_orig: bool = False
    metadata: Mapping | None = None
    metadata_cli: tuple[str, ...] | None = None
    metadata_format: str | None = None
    jobs: int = 1
    tagger: str | None = None
    theme: str | None = "gruvbox-dark"


@dataclass(frozen=True, slots=True)
class ReadSettings:
    """Which metadata sources to load and in what merge order."""

    formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    except_formats: frozenset[str] | None = None  # YAML key: "except"
    # Merge precedence (None = ``MetadataSources`` enum order). Expert
    # knob; YAML-only.
    merge_order: "tuple[MetadataSources, ...] | None" = None


class MergeMode(str, Enum):
    """
    How caller-supplied metadata merges into a comic's existing tags.

    Applies to metadata the caller handed to this run — the write API's
    patch, ``-m``, ``--import`` files and the config's metadata block.
    Metadata comicbox discovered on its own is always accumulated
    additively.

    - ``additive``: deep-merge via mergedeep ADDITIVE. Dicts recurse;
      lists / tuples / sets at conflicting paths *concatenate*; scalars
      and other leaves *replace*. Default.
    - ``replace``: deep-merge via mergedeep REPLACE. Dicts recurse;
      everything else (scalars, lists, tuples, sets) *replaces*. Use it
      when a list-typed patch value is meant to be the new complete
      value rather than an append.
    - ``update``: ``dict.update()`` at ROOT_TAG. Replaces top-level keys
      wholesale; siblings of a replaced key are dropped. A patch of
      ``{"credits": {"Jane": {...}}}`` removes every other credit.

    ``additive`` and ``replace`` differ only on the five list-typed
    schema fields: ``remainders``, ``reprints``, ``series_groups``,
    ``urls`` and ``series.alternative_names``. Everywhere else the
    schema is dict-of-dict or scalar, where the two are
    indistinguishable.
    """

    ADDITIVE = "additive"
    UPDATE = "update"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class WriteSettings:
    """Which metadata formats to write back, and how."""

    formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    # How supplied metadata overlays existing tags. Settable with the
    # ``write.merge_mode`` config key and ``--merge-mode``.
    merge_mode: MergeMode = MergeMode.ADDITIVE
    stamp: bool = False
    stamp_notes: bool = True
    delete_all_tags: bool = False


@dataclass(frozen=True, slots=True)
class PrintSettings:
    """Phases to print and whether to validate."""

    phases: "frozenset[PrintPhases]" = field(default_factory=frozenset)
    validate: bool = False


@dataclass(frozen=True, slots=True)
class ConvertSettings:
    """Archive conversion actions: cbz, rename, page/cover extraction, import/export."""

    cbz: bool | None = None
    rename: bool | None = None
    extract_pages_from: int | None = None
    extract_pages_to: int | None = None
    extract_covers: bool | None = None
    import_paths: tuple[Path, ...] = ()
    export_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    pdf_pages: str = ""


@dataclass(frozen=True, slots=True)
class ComputeSettings:
    """Derived-metadata switches. YAML-only — set-once preferences."""

    pages: bool = False
    page_count: bool = True


@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    """Typed runtime config for comicbox, organized by verb taxonomy."""

    general: GeneralSettings
    read: ReadSettings
    write: WriteSettings
    print: PrintSettings
    convert: ConvertSettings
    compute: ComputeSettings
    online: "OnlineSettings"

    # CLI positional args.
    paths: tuple[str | Path | None, ...] = ()

    # Computed (derived in compute_config(); kept flat for ergonomics —
    # they're read by many call sites and the flat names are clearer).
    all_write_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    read_filename_formats: "frozenset[MetadataFormats]" = field(
        default_factory=frozenset
    )
    read_file_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    read_metadata_lower_filenames: frozenset[str] = field(default_factory=frozenset)
    is_read_comments: bool = False
    is_skip_computed_from_tags: bool = False
