"""Read and layer config sources."""

from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path

from confuse import Configuration
from loguru import logger


def _config_path(args: Namespace | Mapping) -> str | Path | None:
    """
    Pull ``comicbox.general.config`` out of either args shape.

    ``-c/--config`` parses to the ``general_config`` dest, which
    ``post_process_args`` folds into ``args.comicbox.general.config``.
    Look it up explicitly: a blanket ``suppress(AttributeError)`` here
    is what let the key path drift out of sync silently.
    """
    if isinstance(args, Namespace):
        comicbox = getattr(args, "comicbox", None)
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
    config: Configuration, args: Namespace | Mapping | None
) -> None:
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

    # Args (highest priority — must override config files and env vars).
    # Mapping uses .set() so it lands on top of the source stack like
    # set_args() does for Namespace; .add() would put it BELOW the
    # config_default.yaml loaded by .read() above.
    if args:
        if isinstance(args, Mapping):
            config.set(args)
        elif isinstance(args, Namespace):  # pyright: ignore[reportUnnecessaryIsInstance]
            config.set_args(args)
