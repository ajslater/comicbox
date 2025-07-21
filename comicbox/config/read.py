"""Read and layer config sources."""

import contextlib
from argparse import Namespace
from collections.abc import Mapping

from confuse import Configuration
from confuse.templates import AttrDict
from loguru import logger


def _add_config_file(args, config):
    with contextlib.suppress(AttributeError, KeyError):
        if config_fn := (
            args.comicbox.config
            if isinstance(args, Namespace)
            else args["comicbox"]["config"]
        ):
            config.set_file(config_fn)


def read_config_sources(config: Configuration, args: Namespace | Mapping | None):
    """Read config sources in order."""
    # Default System and User configs
    try:
        config.read()
    except Exception as exc:
        logger.warning(exc)

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
