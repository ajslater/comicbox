"""Confuse config for comicbox."""

from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from confuse import Configuration
from confuse.templates import (
    Choice,
    Integer,
    MappingTemplate,
    OneOf,
    Optional,
    Sequence,
    String,
)

from comicbox.config.computed import compute_config
from comicbox.config.paths import (
    expand_glob_paths,
    post_process_set_for_path,
)
from comicbox.config.read import read_config_sources
from comicbox.config.settings import ComicboxSettings, ComputedSettings
from comicbox.version import PACKAGE_NAME

try:
    from pdffile import PageFormat
except ImportError:
    from comicbox.pdffile_stub import PageFormat


_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "compute_pages": bool,
                "compute_page_count": bool,
                "config": Optional(OneOf((str, Path))),
                "delete_all_tags": bool,
                "delete_keys": Optional(OneOf((frozenset, Sequence(str)))),
                "delete_orig": bool,
                "dest_path": OneOf((str, Path)),
                "dry_run": bool,
                "loglevel": OneOf((String(), Integer())),
                "metadata": Optional(dict),
                "metadata_format": Optional(str),
                "metadata_cli": Optional(Sequence(str)),
                "pdf_page_format": Choice(("", *(e.value for e in PageFormat))),
                "read": Optional(frozenset, Sequence(str)),
                "read_ignore": Optional(OneOf((frozenset, Sequence(str)))),
                "recurse": bool,
                "replace_metadata": bool,
                "stamp": bool,
                "stamp_notes": bool,
                "tagger": Optional(str),
                "theme": Optional(str),
                # Actions
                "cbz": Optional(bool),
                "covers": Optional(bool),
                "export": Optional(OneOf((frozenset, Sequence(str)))),
                "import_paths": Optional(Sequence(OneOf((str, Path)))),
                "index_from": Optional(int),
                "index_to": Optional(int),
                "print": Optional(OneOf((frozenset, str))),
                "rename": Optional(bool),
                "validate": Optional(bool),
                "write": Optional(OneOf((frozenset, Sequence(str)))),
                # Targets
                "paths": Optional(OneOf((Sequence(OneOf((str, Path))), None))),
                # Computed
                "computed": Optional(
                    MappingTemplate(
                        {
                            "all_write_formats": frozenset,
                            "read_filename_formats": frozenset,
                            "read_file_formats": frozenset,
                            "read_metadata_lower_filenames": frozenset,
                            "is_read_comments": bool,
                            "is_skip_computed_from_tags": bool,
                        }
                    )
                ),
            }
        )
    }
)


def _build_computed_settings(computed: Any) -> ComputedSettings:
    return ComputedSettings(
        all_write_formats=frozenset(computed.all_write_formats),
        read_filename_formats=frozenset(computed.read_filename_formats),
        read_file_formats=frozenset(computed.read_file_formats),
        read_metadata_lower_filenames=frozenset(computed.read_metadata_lower_filenames),
        is_read_comments=bool(computed.is_read_comments),
        is_skip_computed_from_tags=bool(computed.is_skip_computed_from_tags),
    )


def _build_settings(ad: Any) -> ComicboxSettings:
    """Convert a validated, computed confuse AttrDict into a ComicboxSettings dataclass."""
    inner: Any = ad.comicbox
    metadata_cli = inner.metadata_cli
    return ComicboxSettings(
        # Options
        compute_pages=bool(inner.compute_pages),
        compute_page_count=bool(inner.compute_page_count),
        config=inner.config,
        delete_all_tags=bool(inner.delete_all_tags),
        delete_keys=frozenset(inner.delete_keys or ()),
        delete_orig=bool(inner.delete_orig),
        dest_path=inner.dest_path,
        dry_run=bool(inner.dry_run),
        loglevel=inner.loglevel,
        metadata=inner.metadata,
        metadata_format=inner.metadata_format,
        metadata_cli=tuple(metadata_cli) if metadata_cli else None,
        pdf_page_format=inner.pdf_page_format,
        read=frozenset(inner.read or ()),
        read_ignore=frozenset(inner.read_ignore) if inner.read_ignore else None,
        recurse=bool(inner.recurse),
        replace_metadata=bool(inner.replace_metadata),
        stamp=bool(inner.stamp),
        stamp_notes=bool(inner.stamp_notes),
        tagger=inner.tagger,
        theme=inner.theme,
        # Actions
        cbz=inner.cbz,
        covers=inner.covers,
        export=frozenset(inner.export or ()),
        import_paths=expand_glob_paths(inner.import_paths),
        index_from=inner.index_from,
        index_to=inner.index_to,
        print=frozenset(inner.print or ()),
        rename=inner.rename,
        validate=inner.validate,
        write=frozenset(inner.write or ()),
        # Targets
        paths=tuple(inner.paths or ()),
        # Computed
        computed=_build_computed_settings(inner.computed),
    )


def get_config(
    args: Namespace | Mapping | ComicboxSettings | None = None,
    *,
    modname: str = PACKAGE_NAME,
    path: str | Path | None = None,
    box: bool = False,
) -> ComicboxSettings:
    """
    Get the config dict, layering env and args over defaults.

    Setting the box arg to True reconfigures attributes based on path or no path.
    """
    if isinstance(args, ComicboxSettings):
        # Already a config
        return post_process_set_for_path(args, path, box=box)
    if isinstance(args, Mapping):
        args = dict(args)

    # Read Sources
    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    read_config_sources(config, args)

    # Compute
    config_program = config[PACKAGE_NAME]
    compute_config(config_program)

    ad = config.get(_TEMPLATE)
    settings = _build_settings(ad)
    return post_process_set_for_path(settings, path, box=box)
