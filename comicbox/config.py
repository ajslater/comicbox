"""Confuse config for comicbox."""

import contextlib
from argparse import Namespace
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path

from confuse import Configuration, Integer, OneOf, String
from confuse.templates import AttrDict, MappingTemplate, Optional, Sequence

from comicbox.logger import init_logging
from comicbox.print import PrintPhases
from comicbox.sources import MetadataSources
from comicbox.version import DEFAULT_TAGGER, PACKAGE_NAME

LOG = getLogger(__name__)

_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "compute_pages": bool,
                "config": Optional(str),
                "delete": bool,
                "delete_keys": Optional(Sequence(str)),
                "delete_orig": bool,
                "dest_path": str,
                "dry_run": bool,
                "loglevel": OneOf((String(), Integer())),
                "metadata": Optional(dict),
                "metadata_cli": Optional(Sequence(str)),
                "read": Optional(Sequence(str)),
                "read_ignore": Optional(Sequence(str)),
                "recurse": bool,
                "replace_metadata": bool,
                "stamp_notes": bool,
                "tagger": Optional(str),
                # API Options
                "close_fd": bool,
                # Actions
                "cbz": Optional(bool),
                "cover": Optional(bool),
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
_WRITABLE_SOURCE_KEYS = frozenset({"write", "export"})
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
                LOG.warn(f"{path} is a directory. Ignored without --recurse.")
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


def _get_sources_from_keys(key, keys, ignore_keys):
    """Get sources from keys."""
    sources = []
    writable = key in _WRITABLE_SOURCE_KEYS
    for source in MetadataSources:
        config_keys = source.value.transform_class.SCHEMA_CLASS.CONFIG_KEYS
        if (not writable or source.value.writable) and (
            not source.value.configurable
            or (bool(keys & config_keys) and not bool(config_keys & ignore_keys))
        ):
            sources.append(source)
        if source.value.configurable:
            keys -= source.value.transform_class.SCHEMA_CLASS.CONFIG_KEYS
    return sources, keys


def _set_config_sources_from_keys(config, key):
    """Return a set of schemas from a sequence of config keys."""
    # Keys to set
    keys = config[key] or ()
    keys = frozenset({str(key).strip() for key in keys})

    # Ignore list to set
    attr = f"{key}_ignore"
    ignore_list = getattr(config, attr, ())
    ignore_keys = frozenset({str(key).strip() for key in ignore_list})

    sources, keys = _get_sources_from_keys(key, keys, ignore_keys)

    # Report on invalid formats.
    if keys:
        plural = "s" if len(keys) > 1 else ""
        keys_str = ", ".join(sorted(keys))
        LOG.warning(f"Action '{key}' received invalid format{plural}: {keys_str}")

    return frozenset(sources)


def _transform_keys_to_sources(config):
    """Transform schema config keys to sources."""
    config.read = _set_config_sources_from_keys(config, "read")
    if config.delete:
        config.write = config.export = frozenset()
    else:
        config.write = _set_config_sources_from_keys(config, "write")
    config.export = _set_config_sources_from_keys(config, "export")
    config.all_write_sources = frozenset(config.write | config.export)


def _deduplicate_delete_keys(config):
    """Transform delete keys to a set."""
    config.delete_keys = frozenset(config.delete_keys)


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


def _read_config_sources(config, args):
    """Read config sources in order."""
    # Default System and User configs
    try:
        config.read()
    except Exception as exc:
        LOG.warning(exc)

    # Args Specified Config File
    if args:
        with contextlib.suppress(AttributeError, KeyError):
            if isinstance(args, Namespace):
                config_fn = args.comicbox.config
            elif isinstance(args, Mapping):
                config_fn = args["comicbox"]["config"]
            else:
                config_fn = None
            if config_fn:
                config.set_file(config_fn)

    # Env vars
    config.set_env()

    # Args
    if args:
        if isinstance(args, Mapping):
            config.add(args)
        if isinstance(args, Namespace):
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

    # Read Sources
    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    _read_config_sources(config, args)

    # Create config
    ad = config.get(_TEMPLATE)
    ad_config = ad.comicbox  # type: ignore[reportAttributeAccessIssue]

    # Post Process Config
    _clean_paths(ad_config)
    _ensure_cli_yaml(ad_config)
    _transform_keys_to_sources(ad_config)
    _deduplicate_delete_keys(ad_config)
    _parse_print(ad_config)
    _set_tagger(ad_config)
    init_logging(ad_config.loglevel)
    return ad_config
