"""Confuse config for comicbox."""

from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path

from confuse import Configuration
from confuse.templates import (
    AttrDict,
    Integer,
    MappingTemplate,
    OneOf,
    Optional,
    Sequence,
    String,
)

from comicbox.config.computed import compute_config
from comicbox.config.paths import post_process_set_for_path
from comicbox.config.read import read_config_sources
from comicbox.version import PACKAGE_NAME

_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "compute_pages": bool,
                "config": Optional(OneOf((str, Path))),
                "delete_all_tags": bool,
                "delete_keys": Optional([frozenset, Sequence(str)]),
                "delete_orig": bool,
                "dest_path": OneOf((str, Path)),
                "dry_run": bool,
                "loglevel": OneOf((String(), Integer())),
                "metadata": Optional(dict),
                "metadata_format": Optional(str),
                "metadata_cli": Optional(Sequence(str)),
                "read": Optional([frozenset, Sequence(str)]),
                "read_ignore": Optional([frozenset, Sequence(str)]),
                "recurse": bool,
                "replace_metadata": bool,
                "stamp": bool,
                "stamp_notes": bool,
                "tagger": Optional(str),
                "theme": Optional(str),
                # API Options
                "close_fd": bool,
                # Actions
                "cbz": Optional(bool),
                "covers": Optional(bool),
                "export": Optional([frozenset, Sequence(str)]),
                "import_paths": Optional(Sequence(OneOf((str, Path)))),
                "index_from": Optional(int),
                "index_to": Optional(int),
                "print": Optional([frozenset, str]),
                "rename": Optional(bool),
                "write": Optional([frozenset, Sequence(str)]),
                # Targets
                "paths": Optional(Sequence(OneOf((str, Path, None)))),
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


def get_config(
    args: Namespace | Mapping | AttrDict | None = None,
    *,
    modname: str = PACKAGE_NAME,
    path: str | Path | None = None,
    box: bool = False,
) -> AttrDict:
    """
    Get the config dict, layering env and args over defaults.

    Setting the box arg to True reconfigures attributes based on path or no path.
    """
    if isinstance(args, AttrDict):
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

    # Create config
    ad: AttrDict = config.get(_TEMPLATE)  # pyright: ignore[reportAssignmentType]
    return post_process_set_for_path(ad.comicbox, path, box=box)
