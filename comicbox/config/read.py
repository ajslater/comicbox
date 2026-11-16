"""Read and layer config sources."""

import os
from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path

from confuse import Configuration, EnvSource
from confuse.templates import (
    MappingTemplate,
    OneOf,
    Optional,
    Sequence,
    String,
    Template,
    TypeTemplate,
)
from loguru import logger

from comicbox.version import PACKAGE_NAME

_ENV_PREFIX = f"{PACKAGE_NAME.upper()}_"
_ENV_SEP = "__"

# Env vars that used to be read by a bespoke parser and now have no
# meaning. Warn rather than ignore: a stale COMICBOX_METRON_KEY that
# silently stops authenticating is the same silent-drift class of defect
# as the -c bug.
_LEGACY_ENV_VARS: Mapping[str, str] = {
    "COMICBOX_ONLINE_MATCH": "COMICBOX_ONLINE__LOOKUP__MATCH",
    "COMICBOX_ONLINE_PROMPTS": "COMICBOX_ONLINE__LOOKUP__PROMPTS",
    "COMICBOX_ONLINE_REMATCH": "COMICBOX_ONLINE__LOOKUP__REMATCH",
    "COMICBOX_ONLINE_FIRST_WINS": "COMICBOX_ONLINE__LOOKUP__FIRST_WINS",
    "COMICBOX_ONLINE_SOURCES": "COMICBOX_ONLINE__LOOKUP__SOURCES",
    "COMICBOX_ONLINE_CACHE": "COMICBOX_ONLINE__CACHE__MODE",
    "COMICBOX_ONLINE_CACHE_DIR": "COMICBOX_ONLINE__CACHE__DIR",
    "COMICBOX_ONLINE_CACHE_TTL": "COMICBOX_ONLINE__CACHE__TTL",
    "COMICBOX_ONLINE_AUTO_THRESHOLD": "COMICBOX_ONLINE__TUNING__AUTO_THRESHOLD",
    "COMICBOX_ONLINE_EFFORT": "COMICBOX_ONLINE__TUNING__EFFORT",
    "COMICBOX_ONLINE_RETRY_BUDGET": "COMICBOX_ONLINE__TUNING__RETRY_BUDGET",
    # No source takes a user or password any more; both mean the key.
    "COMICBOX_METRON_USER": "COMICBOX_ONLINE__AUTH__METRON__KEY",
    "COMICBOX_METRON_PASS": "COMICBOX_ONLINE__AUTH__METRON__KEY",
    "COMICBOX_METRON_KEY": "COMICBOX_ONLINE__AUTH__METRON__KEY",
    "COMICBOX_METRON_URL": "COMICBOX_ONLINE__AUTH__METRON__URL",
    "COMICBOX_COMICVINE_USER": "COMICBOX_ONLINE__AUTH__COMICVINE__KEY",
    "COMICBOX_COMICVINE_PASS": "COMICBOX_ONLINE__AUTH__COMICVINE__KEY",
    "COMICBOX_COMICVINE_KEY": "COMICBOX_ONLINE__AUTH__COMICVINE__KEY",
    "COMICBOX_COMICVINE_URL": "COMICBOX_ONLINE__AUTH__COMICVINE__URL",
}


def _warn_legacy_env_vars(env: Mapping[str, str]) -> None:
    """Warn about env vars whose flat spelling is no longer read."""
    for old, new in _LEGACY_ENV_VARS.items():
        if old in env:
            logger.warning(f"{old} is no longer read. Use {new} instead.")


_CONTAINER_TYPES = frozenset({list, tuple, set, frozenset})
# How a list-valued setting takes one string from the environment, as the CLI
# takes its option: split on commas, as -w is, or whole, as -m and -i are.
_SPLIT = "split"
_WHOLE = "whole"


def _takes_a_string(template: Template) -> bool:
    return isinstance(template, String) or (
        isinstance(template, TypeTemplate) and template.typ is str
    )


def _list_kind(template: Template | None) -> str | None:
    """
    Say how a setting reads a list from one string, or None if it is no list.

    A setting that also accepts a string, such as print phases or online
    sources, gives it a meaning of its own, and is left alone.
    """
    if isinstance(template, Optional):
        template = template.subtemplate
    if isinstance(template, Sequence):
        return _WHOLE
    if isinstance(template, TypeTemplate):
        return _SPLIT if template.typ in _CONTAINER_TYPES else None
    if isinstance(template, OneOf):
        return _one_of_kind(template)
    return None


def _one_of_kind(template: OneOf) -> str | None:
    """Say how a choice of templates reads a list from one string."""
    allowed = list(template.allowed)
    if any(_takes_a_string(sub) for sub in allowed):
        return None
    kinds = {_list_kind(sub) for sub in allowed} - {None}
    if _WHOLE in kinds:
        return _WHOLE
    return _SPLIT if kinds else None


def _lists_from_strings(values: Mapping, template: Template | None) -> dict:
    """
    Read a plain environment string at a list-valued setting as that list.

    ``COMICBOX_WRITE__FORMATS=cix,mi`` was read one character at a time;
    only the indexed ``COMICBOX_WRITE__FORMATS__0=cix`` worked.
    """
    if isinstance(template, Optional):
        template = template.subtemplate
    subtemplates = (
        template.subtemplates if isinstance(template, MappingTemplate) else {}
    )
    read: dict = {}
    for key, value in values.items():
        sub = subtemplates.get(key)
        if isinstance(value, Mapping):
            read[key] = _lists_from_strings(value, sub)
        elif isinstance(value, str) and (kind := _list_kind(sub)):
            if kind == _SPLIT:
                read[key] = [item.strip() for item in value.split(",") if item.strip()]
            else:
                read[key] = [value]
        else:
            read[key] = value
    return read


def _add_env(config: Configuration, template: Template | None = None) -> None:
    """
    Overlay env vars onto the config tree.

    The whole tree hangs off the ``comicbox`` key, so mounting the
    EnvSource there is what makes ``COMICBOX_GENERAL__RECURSE`` land on
    ``comicbox.general.recurse``. Confuse's own ``set_env()`` mounts at
    the root, which would have required writing the package name twice
    (``COMICBOX_COMICBOX__GENERAL__RECURSE``) — so it read nothing and
    every real env knob had to be hand-parsed elsewhere.

    EnvSource lowercases keys after the prefix, splits on ``__``, and
    parses values as YAML scalars, so types match the YAML file layer. A
    plain string at a list-valued setting of ``template`` is read as the
    CLI reads that option (``_lists_from_strings``).
    """
    _warn_legacy_env_vars(os.environ)
    env_source = EnvSource(_ENV_PREFIX, sep=_ENV_SEP, loader=config.loader)
    config.set({PACKAGE_NAME: _lists_from_strings(dict(env_source), template)})


def _config_path(args: Namespace | Mapping) -> str | Path | None:
    """
    Pull ``comicbox.general.config`` out of any args shape.

    This runs before ``set_args``, so it reads raw args rather than the
    config tree and has to know all three shapes: the CLI's dotted dest
    (``-c`` parses straight to ``general.config``), a library caller's
    nested Namespace, and a Mapping. Look each up explicitly: a blanket
    ``suppress(AttributeError)`` here is what let the key path drift out
    of sync silently.
    """
    if isinstance(args, Namespace):
        comicbox = getattr(args, "comicbox", None)
        if dotted := getattr(comicbox, "general.config", None):
            return dotted
        general = getattr(comicbox, "general", None)
        return getattr(general, "config", None)
    comicbox = args.get("comicbox")
    if not isinstance(comicbox, Mapping):
        return None
    general = comicbox.get("general")
    if not isinstance(general, Mapping):
        return None
    config_fn = general.get("config")
    return config_fn if isinstance(config_fn, str | Path) else None


def _add_config_file(args: Namespace | Mapping, config: Configuration) -> None:
    if config_fn := _config_path(args):
        # confuse's set_file takes a str; the config key accepts either.
        config.set_file(str(config_fn))


def read_config_sources(
    config: Configuration,
    args: Namespace | Mapping | None,
    template: Template | None = None,
) -> None:
    """Read config sources in order; ``template`` is the package's settings."""
    # User config, then the package defaults beneath it. Read separately:
    # confuse's read() adds them in that order, so a malformed user file
    # raised before the defaults were ever added and validation then died
    # on "comicbox.paths not found" instead of the user file being skipped.
    try:
        config.read(user=True, defaults=False)
    except Exception as exc:
        logger.warning(f"Ignoring user config: {exc}")
    config.read(user=False, defaults=True)

    # Args Specified Config File
    if args:
        _add_config_file(args, config)

    # Env vars
    _add_env(config, template)

    # Args (highest priority — must override config files and env vars).
    # Mapping uses .set() so it lands on top of the source stack like
    # set_args() does for Namespace; .add() would put it BELOW the
    # config_default.yaml loaded by .read() above.
    if args:
        if isinstance(args, Mapping):
            config.set(args)
        elif isinstance(args, Namespace):  # pyright: ignore[reportUnnecessaryIsInstance]
            # dots=True splits the CLI's dotted dests into the config tree.
            config.set_args(args, dots=True)
