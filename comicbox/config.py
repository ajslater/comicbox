"""Confuse config for comicbox."""

import contextlib
from argparse import Namespace
from collections.abc import Iterable, Mapping
from logging import getLogger
from pathlib import Path

from confuse import Configuration, Subview
from confuse.templates import (
    AttrDict,
    Integer,
    MappingTemplate,
    OneOf,
    Optional,
    Sequence,
    String,
)

from comicbox.formats import MetadataFormats
from comicbox.print import PrintPhases
from comicbox.sources import MetadataSources
from comicbox.version import DEFAULT_TAGGER, PACKAGE_NAME

LOG = getLogger(__name__)

_FORMATS_WITH_TAGS_WITHOUT_IDS = frozenset(
    {
        MetadataFormats.COMIC_BOOK_INFO,
        MetadataFormats.COMIC_INFO,
        MetadataFormats.COMICTAGGER,
        MetadataFormats.PDF,
        MetadataFormats.PDF_XML,
    }
)


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
_SINGLE_NO_PATH = (None,)


def _clean_paths(config: Subview):
    """No null paths. Turn off options for no paths."""
    paths: Iterable[str | Path] | None = config["paths"].get()  # pyright: ignore[reportAssignmentType]
    paths_removed = False
    if paths:
        filtered_paths = set()
        for path in paths:
            if not path:
                continue
            if Path(path).is_dir() and not config["recurse"].get(bool):
                LOG.warning(f"{path} is a directory. Ignored without --recurse.")
                paths_removed = True
                continue
            filtered_paths.add(path)
        paths = tuple(sorted(filtered_paths))
    if paths or paths_removed:
        if not paths:
            LOG.error("No valid paths left.")
        final_paths = paths
    else:
        final_paths = _SINGLE_NO_PATH
    config["paths"].set(final_paths)


def _ensure_cli_yaml(config):
    """Wrap all cli yaml in brackets if its bare."""
    mds = config["metadata_cli"].get()
    if not mds:
        return
    wrapped_md_list = []
    for md in mds:
        if not md:
            continue
        wrapped_md = "{" + md + "}" if md[0] != "{" else md
        wrapped_md_list.append(wrapped_md)

    config["metadata_cli"].set(tuple(wrapped_md_list))


def _get_formats_from_keys(keys, ignore_keys):
    """Get sources from keys."""
    fmts = []
    for fmt in MetadataFormats:
        format_keys = fmt.value.config_keys
        if fmt.value.enabled and (not ignore_keys & format_keys and keys & format_keys):
            fmts.append(fmt)
        keys -= format_keys
        ignore_keys -= format_keys
    return fmts, keys


def _get_config_formats_from_keys(config, key):
    """Return a set of schemas from a sequence of config keys."""
    # Keys to set
    keys = config[key] or ()
    keys = frozenset({str(key).strip() for key in keys})

    # Ignore list to set
    attr = f"{key}_ignore"
    ignore_list = getattr(config, attr, ())
    ignore_keys = frozenset({str(key).strip() for key in ignore_list})
    fmts, keys = _get_formats_from_keys(keys, ignore_keys)

    # Report on invalid formats.
    if keys:
        plural = "s" if len(keys) > 1 else ""
        keys_str = ", ".join(sorted(keys))
        LOG.warning(f"Action '{key}' received invalid format{plural}: {keys_str}")

    return frozenset(fmts)


def _transform_keys_to_formats(config: Subview):
    """Transform schema config keys to format enums."""
    if config["delete_all_tags"].get(bool):
        config["read"].set(frozenset())
        config["write"].set(frozenset())
        config["export"].set(frozenset())
    else:
        read_fmts = _get_config_formats_from_keys(config, "read")
        read_ignore = config["read_ignore"].get()
        if read_ignore and (
            read_ignore_fmts := _get_config_formats_from_keys(config, "read_ignore")
        ):
            read_fmts -= read_ignore_fmts
        config["read"].set(read_fmts)
        write_fmts = _get_config_formats_from_keys(config, "write")
        config["write"].set(write_fmts)
        export_fmts = _get_config_formats_from_keys(config, "export")
        config["export"] = export_fmts


def _deduplicate_delete_keys(config: Subview):
    """Transform delete keys to a set."""
    delete_keys: list | set | tuple | frozenset = config["delete_keys"].get(list)  # pyright: ignore[reportAssignmentType]
    delete_keys = frozenset({kp.removeprefix("comicbox.") for kp in delete_keys})
    config["delete_keys"].set(delete_keys)


def _parse_print(config: Subview):
    print_fmts: str | None = config["print"].get()  # pyright: ignore[reportAssignmentType]
    if not print_fmts:
        print_fmts = ""
    print_phases = print_fmts.lower()
    enum_print_phases = set()
    for phase in print_phases:
        try:
            enum = PrintPhases(phase)
            enum_print_phases.add(enum)
        except ValueError as exc:
            LOG.warning(exc)
    print_fmts_set = frozenset(enum_print_phases)
    config["print"].set(print_fmts_set)


def _add_config_file(args, config):
    with contextlib.suppress(AttributeError, KeyError):
        if config_fn := (
            args.comicbox.config
            if isinstance(args, Namespace)
            else args["comicbox"]["config"]
        ):
            config.set_file(config_fn)


def _read_config_sources(config: Configuration, args: Namespace | Mapping | None):
    """Read config sources in order."""
    # Default System and User configs
    try:
        config.read()
    except Exception as exc:
        LOG.warning(exc)

    # Args Specified Config File
    if args:
        _add_config_file(args, config)

    # Env vars
    config.set_env()

    # Args
    if args:
        if isinstance(args, Mapping | AttrDict):
            config.add(args)
        elif isinstance(args, Namespace):  # pyright: ignore[reportUnnecessaryIsInstance]
            config.set_args(args)


def _set_tagger(config: Subview):
    tagger = config["tagger"].get()
    if not tagger:
        config["tagger"].set(DEFAULT_TAGGER)


def _set_computed(config):
    all_write_fmts = frozenset(config["write"].get() | config["export"].get())
    config["computed"]["all_write_formats"].set(all_write_fmts)
    read = config["read"].get()
    rfnf = frozenset(frozenset(MetadataSources.ARCHIVE_FILENAME.value.formats) & read)
    config["computed"]["read_filename_formats"].set(rfnf)
    rff = frozenset(frozenset(MetadataSources.ARCHIVE_FILE.value.formats) & read)
    config["computed"]["read_file_formats"].set(rff)
    rmlf = frozenset(fmt.value.filename.lower() for fmt in rff)
    config["computed"]["read_metadata_lower_filenames"].set(rmlf)
    irc = bool(
        frozenset(frozenset(MetadataSources.ARCHIVE_COMMENT.value.formats) & read)
    )
    config["computed"]["is_read_comments"].set(irc)
    iscft = not bool(_FORMATS_WITH_TAGS_WITHOUT_IDS & read)
    config["computed"]["is_skip_computed_from_tags"].set(iscft)


def get_config(
    args: Namespace | Mapping | AttrDict | None = None,
    modname: str = PACKAGE_NAME,
) -> AttrDict:
    """Get the config dict, layering env and args over defaults."""
    if isinstance(args, AttrDict):
        # Already a config
        return args
    if isinstance(args, Mapping):
        args = dict(args)

    # Read Sources
    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    _read_config_sources(config, args)
    config_program = config[PACKAGE_NAME]

    _clean_paths(config_program)
    _ensure_cli_yaml(config_program)
    _deduplicate_delete_keys(config_program)
    _transform_keys_to_formats(config_program)
    _set_computed(config_program)
    _parse_print(config_program)
    _set_tagger(config_program)

    # Create config
    ad: AttrDict = config.get(_TEMPLATE)  # pyright: ignore[reportAssignmentType]
    return ad.comicbox
