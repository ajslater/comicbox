"""Confuse config for comicbox."""

import contextlib
from argparse import Namespace
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path

from confuse import Configuration, Integer, OneOf, String
from confuse.templates import AttrDict, MappingTemplate, Optional, Sequence

from comicbox.formats import MetadataFormats
from comicbox.logger import init_logging
from comicbox.print import PrintPhases
from comicbox.version import DEFAULT_TAGGER, PACKAGE_NAME

LOG = getLogger(__name__)

_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "compute_pages": bool,
                "config": Optional(OneOf((str, Path))),
                "delete_all_tags": bool,
                "delete_keys": Optional(Sequence(str)),
                "delete_orig": bool,
                "dest_path": OneOf((str, Path)),
                "dry_run": bool,
                "loglevel": OneOf((String(), Integer())),
                "metadata": Optional(dict),
                "metadata_format": Optional(str),
                "metadata_cli": Optional(Sequence(str)),
                "read": Optional(Sequence(str)),
                "read_ignore": Optional(Sequence(str)),
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
                "export": Optional(Sequence(str)),
                "import_paths": Optional(Sequence(OneOf((str, Path)))),
                "index_from": Optional(int),
                "index_to": Optional(int),
                "print": Optional(str),
                "rename": Optional(bool),
                "write": Optional(Sequence(str)),
                # Targets
                "paths": Optional(Sequence(OneOf((str, Path)))),
            }
        )
    }
)
_SINGLE_NO_PATH = (None,)


def _clean_paths(config):
    """No null paths. Turn off options for no paths."""
    paths = config.paths
    paths_removed = False
    if paths:
        filtered_paths = set()
        for path in paths:
            if not path:
                continue
            if Path(path).is_dir() and not config.recurse:
                LOG.warning(f"{path} is a directory. Ignored without --recurse.")
                paths_removed = True
                continue
            filtered_paths.add(path)
        if paths:
            paths = tuple(sorted(filtered_paths))
    if paths or paths_removed:
        if not paths:
            LOG.error("No valid paths left.")
        config.paths = paths
    else:
        config.paths = _SINGLE_NO_PATH


def _ensure_cli_yaml(config):
    """Wrap all cli yaml in brackets if its bare."""
    if not config.metadata_cli:
        return
    wrapped_md_list = []
    for md in config.metadata_cli:
        if not md:
            continue
        wrapped_md = "{" + md + "}" if md[0] != "{" else md
        wrapped_md_list.append(wrapped_md)

    config.metadata_cli = wrapped_md_list


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


def _set_config_formats_from_keys(config, key):
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


def _transform_keys_to_formats(config):
    """Transform schema config keys to format enums."""
    config.read = _set_config_formats_from_keys(config, "read")
    if config.delete_all_tags:
        config.write = config.export = frozenset()
    else:
        config.write = _set_config_formats_from_keys(config, "write")
    config.export = _set_config_formats_from_keys(config, "export")
    config.all_write_formats = frozenset(config.write | config.export)


def _deduplicate_delete_keys(config):
    """Transform delete keys to a set."""
    config.delete_keys = frozenset(
        sorted({kp.removeprefix("comicbox.") for kp in config.delete_keys})
    )


def _parse_print(config):
    if not config.print:
        config.print = ""
    print_phases = config.print.lower()
    enum_print_phases = set()
    for phase in print_phases:
        try:
            enum = PrintPhases(phase)
            enum_print_phases.add(enum)
        except ValueError as exc:
            LOG.warning(exc)
    config.print = frozenset(enum_print_phases)


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


def _set_tagger(config):
    if not config.tagger:
        config.tagger = DEFAULT_TAGGER


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

    # Create config
    ad: AttrDict = config.get(_TEMPLATE)  # pyright: ignore[reportAssignmentType]
    ad_config = ad.comicbox

    # Post Process Config
    _clean_paths(ad_config)
    _ensure_cli_yaml(ad_config)
    _transform_keys_to_formats(ad_config)
    _deduplicate_delete_keys(ad_config)
    _parse_print(ad_config)
    _set_tagger(ad_config)
    init_logging(ad_config.loglevel)
    return ad_config
