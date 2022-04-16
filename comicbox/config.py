"""Confuse config for comicbox."""
import typing

from argparse import Namespace
from logging import getLogger

from confuse import Configuration
from confuse.templates import AttrDict
from confuse.templates import MappingTemplate

from comicbox.version import PROGRAM_NAME


LOG = getLogger(__name__)


TEMPLATE = MappingTemplate(
    {
        "comicbox": MappingTemplate(
            {
                "comet": bool,
                "comicinfoxml": bool,
                "comicbookinfo": bool,
                "cover": bool,
                "delete_rar": bool,
                "delete_tags": bool,
                "dest_path": str,
                "dry_run": bool,
                "filename": bool,
                "metadata": bool,
                "raw": bool,
                "recurse": bool,
            }
        )
    }
)


def get_config(
    args: typing.Optional[Namespace] = None, modname: str = PROGRAM_NAME
) -> AttrDict:
    """Get the config dict, layering env and args over defaults."""
    config = Configuration(PROGRAM_NAME, modname=modname, read=False)
    try:
        config.read()
    except Exception as exc:
        LOG.warning(exc)
    if args and args.config:
        config.set_file(args.config)
    config.set_env()
    if args:
        config.set_args(args)
    ad = config.get(TEMPLATE)
    if not isinstance(ad, AttrDict):
        raise ValueError()
    return ad.comicbox
