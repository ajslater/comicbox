"""Confuse config for comicbox."""
import typing
from argparse import Namespace
from logging import getLogger

from confuse import Configuration
from confuse.templates import AttrDict, MappingTemplate, Optional, Sequence

from comicbox.version import PACKAGE_NAME

LOG = getLogger(__name__)


TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "comet": bool,
                "comicinfoxml": bool,
                "comicbookinfo": bool,
                "config": Optional(str),
                "delete_orig": bool,
                "delete_tags": bool,
                "dest_path": str,
                "dry_run": bool,
                "filename": bool,
                "raw": bool,
                "recurse": bool,
                "metadata": dict,
                # API Options
                "close_fd": bool,
                "check_unrar": bool,
                # Actions
                "cbz": Optional(bool),
                "covers": Optional(bool),
                "export": Optional(bool),
                "file_type": Optional(bool),
                "import_fn": Optional(str),
                "index_from": Optional(int),
                "print": Optional(bool),
                "rename": Optional(bool),
                "version": Optional(bool),
                # Targets
                "paths": Optional(Sequence(str)),
            }
        )
    }
)


def get_config(
    args: typing.Optional[Namespace] = None, modname: str = PACKAGE_NAME
) -> AttrDict:
    """Get the config dict, layering env and args over defaults."""
    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    try:
        config.read()
    except Exception as exc:
        LOG.warning(exc)
    if args and args.comicbox and args.comicbox.config:
        config.set_file(args.comicbox.config)
    config.set_env()
    if args:
        config.set_args(args)
    ad = config.get(TEMPLATE)
    if not isinstance(ad, AttrDict):
        raise TypeError
    if ad.comicbox.paths:
        ad.comicbox.paths = sorted(frozenset(ad.comicbox.paths))
    return ad.comicbox
