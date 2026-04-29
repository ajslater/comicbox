"""
Typed runtime config for comicbox.

Built once by ``get_config()`` from the validated confuse AttrDict; every
downstream module takes ``Settings`` instead of ``AttrDict``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comicbox.formats import MetadataFormats
    from comicbox.print import PrintPhases


@dataclass(frozen=True, slots=True)
class ComputedSettings:
    """Computed settings derived from raw config in compute_config()."""

    all_write_formats: "frozenset[MetadataFormats]"
    read_filename_formats: "frozenset[MetadataFormats]"
    read_file_formats: "frozenset[MetadataFormats]"
    read_metadata_lower_filenames: frozenset[str]
    is_read_comments: bool
    is_skip_computed_from_tags: bool


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed runtime config for comicbox."""

    # Options
    compute_pages: bool
    compute_page_count: bool
    config: str | Path | None
    delete_all_tags: bool
    delete_keys: frozenset[str]
    delete_orig: bool
    dest_path: str | Path
    dry_run: bool
    loglevel: str | int
    metadata: Mapping | None
    metadata_format: str | None
    metadata_cli: tuple[str, ...] | None
    pdf_page_format: str
    read: "frozenset[MetadataFormats]"
    read_ignore: frozenset[str] | None
    recurse: bool
    replace_metadata: bool
    stamp: bool
    stamp_notes: bool
    tagger: str
    theme: str | None
    # Actions
    cbz: bool | None
    covers: bool | None
    export: "frozenset[MetadataFormats]"
    import_paths: tuple[Path, ...]
    index_from: int | None
    index_to: int | None
    print: "frozenset[PrintPhases]"
    rename: bool | None
    validate: bool | None
    write: "frozenset[MetadataFormats]"
    # Targets
    paths: tuple[str | Path | None, ...]
    # Computed
    computed: ComputedSettings
