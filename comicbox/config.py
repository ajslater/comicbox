"""Confuse config for comicbox."""
import typing

from argparse import Namespace

from confuse import Configuration
from confuse.templates import AttrDict
from confuse.templates import MappingTemplate

from comicbox.version import PROGRAM_NAME


TEMPLATE = MappingTemplate(
    {
        "comet": bool,
        "comicrack": bool,
        "comiclover": bool,
        "cover": bool,
        "delete_rar": bool,
        "delete_tags": bool,
        "dest_path": str,
        "filename": bool,
        "raw": bool,
        "recurse": bool,
    }
)


def get_config(args: typing.Optional[Namespace] = None) -> AttrDict:
    """Get the config dict, layering env and args over defaults."""
    config = Configuration(PROGRAM_NAME, PROGRAM_NAME)
    if args and args.config:
        config.set_file(args.config)
    config.set_env()
    if args:
        config.set_args(args)
    ad = config.get(TEMPLATE)
    if not isinstance(ad, AttrDict):
        raise ValueError()
    return ad
