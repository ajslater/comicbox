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
                "config": Optional(str),
                "delete_orig": bool,
                "delete_tags": bool,
                "dest_path": str,
                "dry_run": bool,
                "raw": bool,
                "read_comet": bool,
                "read_comicinfoxml": bool,
                "read_comicbookinfo": bool,
                "read_filename": bool,
                "read_pdf": bool,
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
                "index_to": Optional(int),
                "print": Optional(bool),
                "rename": Optional(bool),
                "version": Optional(bool),
                "write_comet": bool,
                "write_comicbookinfo": bool,
                "write_comicinfoxml": bool,
                "write_pdf": bool,
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
    if (
        args
        and getattr(args, "comicbox", None)
        and (config_fn := getattr(args.comicbox, "config", None))
    ):
        config.set_file(config_fn)
    config.set_env()
    if args:
        config.set_args(args)
    ad = config.get(TEMPLATE)
    if not isinstance(ad, AttrDict):
        raise TypeError
    if ad.comicbox.paths:
        ad.comicbox.paths = sorted(frozenset(ad.comicbox.paths))
    return ad.comicbox
