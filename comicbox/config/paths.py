"""Configure for paths."""

from collections.abc import Sequence
from dataclasses import replace
from glob import glob
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from confuse import Subview
from loguru import logger

from comicbox.config.settings import Settings
from comicbox.print import PrintPhases

if TYPE_CHECKING:
    from collections.abc import Iterable


_SINGLE_NO_PATH: tuple[str | Path | None, ...] = (None,)
_NO_PATH_ATTRS: MappingProxyType[str, object] = MappingProxyType(
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


def clean_paths(config: Subview) -> None:
    """No null paths. Turn off options for no paths."""
    paths: Iterable[str | Path] | None = config["paths"].get()
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


def _no_path_changes(
    settings: Settings,
) -> tuple[dict[str, object], list[str]]:
    """Compute the per-field overrides that apply when no archive path is set."""
    changes: dict[str, object] = {}
    need_file_opts: list[str] = []
    blocked_print = frozenset(_NO_PATH_PRINT_PHASES) & settings.print
    if blocked_print:
        need_file_opts.extend(f"print {p.name.lower()}" for p in blocked_print)
        changes["print"] = settings.print - blocked_print
    for attr, val in _NO_PATH_ATTRS.items():
        if getattr(settings, attr):
            need_file_opts.append(attr)
            changes[attr] = val
    return changes, need_file_opts


def post_process_set_for_path(
    settings: Settings, path: str | Path | None, *, box: bool
) -> Settings:
    """Turn off options and warn if no path."""
    if path or not box:
        return settings
    changes, need_file_opts = _no_path_changes(settings)
    if need_file_opts:
        plural = "s" if len(need_file_opts) > 1 else ""
        opts = ", ".join(need_file_opts)
        logger.warning(
            f"Cannot perform action{plural} '{opts}' without an archive path."
        )
    return replace(settings, **changes) if changes else settings


def expand_glob_paths(paths: Sequence[str | Path] | None) -> tuple[Path, ...]:
    """Expand glob paths into a tuple of real paths."""
    if not paths:
        return ()
    expanded_paths: set[Path] = set()
    for path in paths:
        path_str = str(path)
        if "*" in path_str:
            expanded_paths |= {Path(expanded_path) for expanded_path in glob(path_str)}  # noqa: PTH207
        else:
            expanded_paths.add(Path(path))
    return tuple(sorted(expanded_paths))
