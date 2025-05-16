"""Configure for paths."""

from copy import copy
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from confuse import Subview
from confuse.templates import AttrDict
from loguru import logger

from comicbox.print import PrintPhases

if TYPE_CHECKING:
    from collections.abc import Iterable


_SINGLE_NO_PATH = (None,)
_NO_PATH_ATTRS = MappingProxyType(
    {
        "index_from": None,
        "index_to": None,
        "write": None,
        "covers": False,
        "cbz": False,
        "delete_all_tags": False,
        "rename": False,
    }
)
_NO_PATH_PRINT_PHASES = (PrintPhases.FILE_TYPE, PrintPhases.FILE_NAMES)


def clean_paths(config: Subview):
    """No null paths. Turn off options for no paths."""
    paths: Iterable[str | Path] | None = config["paths"].get()  # pyright: ignore[reportAssignmentType]
    paths_removed = False
    if paths:
        filtered_paths = set()
        for path in paths:
            if not path:
                continue
            if Path(path).is_dir() and not config["recurse"].get(bool):
                logger.warning(f"{path} is a directory. Ignored without --recurse.")
                paths_removed = True
                continue
            filtered_paths.add(path)
        paths = tuple(sorted(filtered_paths))
    if paths or paths_removed:
        if not paths:
            logger.error("No valid paths left.")
        final_paths = paths
    else:
        final_paths = _SINGLE_NO_PATH
    config["paths"].set(final_paths)


def post_process_set_for_path(config: AttrDict, path: str | Path | None, *, box: bool):
    """Turn off options and warn if no path."""
    if path or not box:
        return config
    need_file_opts = []

    # Alterations in this method are shallow, no need for deepcopy
    config = copy(AttrDict(config))

    for phase in _NO_PATH_PRINT_PHASES:
        if phase in config.print:
            need_file_opts.append(f"print {phase.name.lower()}")
            config.print = frozenset(config.print - {phase})

    for attr, val in _NO_PATH_ATTRS.items():
        if config[attr]:
            need_file_opts.append(attr)
            config[attr] = val

    if need_file_opts:
        plural = "s" if len(need_file_opts) > 1 else ""
        opts = ", ".join(need_file_opts)
        logger.warning(
            f"Cannot perform action{plural} '{opts}' without an archive path."
        )
    return config
