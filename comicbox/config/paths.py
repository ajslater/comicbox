"""Configure for paths."""

from collections.abc import Sequence
from dataclasses import replace
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING, Any

from confuse import Subview
from loguru import logger

from comicbox.config.settings import ComicboxSettings
from comicbox.print import PrintPhases

if TYPE_CHECKING:
    from collections.abc import Iterable


_SINGLE_NO_PATH: tuple[str | Path | None, ...] = (None,)
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
            if Path(path).is_dir() and not config["general"]["recurse"].get(bool):
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


# Per-group field → (need_file_opts label, replacement value, "truthy" predicate).
# When the predicate fires on the current settings, we record the label and
# overlay the replacement onto the group's replace() kwargs.
_CONVERT_NO_PATH_FIELDS: tuple[tuple[str, str, Any], ...] = (
    ("extract_pages_from", "extract_pages_from", None),
    ("extract_pages_to", "extract_pages_to", None),
    ("extract_covers", "extract_covers", False),
    ("cbz", "cbz", False),
    ("rename", "rename", False),
)

_WRITE_NO_PATH_FIELDS: tuple[tuple[str, str, Any], ...] = (
    ("formats", "write", frozenset()),
    ("delete_all_tags", "delete_all_tags", False),
)


def _collect_overrides(
    section: Any,
    fields: tuple[tuple[str, str, Any], ...],
    need_file_opts: list[str],
) -> dict[str, Any]:
    """Gather the per-section replace() kwargs for fields blocked by no-path."""
    overrides: dict[str, Any] = {}
    for attr, label, replacement in fields:
        current = getattr(section, attr)
        if (replacement is None and current is not None) or (
            replacement is not None and current
        ):
            need_file_opts.append(label)
            overrides[attr] = replacement
    return overrides


def _no_path_changes(
    settings: ComicboxSettings,
) -> tuple[dict[str, Any], list[str]]:
    """
    Compute the per-field overrides that apply when no archive path is set.

    Returns a (changes, need_file_opts) pair. ``changes`` maps top-level
    ``ComicboxSettings`` attribute names to replacement values; callers
    apply them with ``dataclasses.replace``.
    """
    changes: dict[str, Any] = {}
    need_file_opts: list[str] = []

    # Print phases that can't run without a file (file-type, file-names).
    blocked_print = frozenset(_NO_PATH_PRINT_PHASES) & settings.print.phases
    if blocked_print:
        need_file_opts.extend(f"print {p.name.lower()}" for p in blocked_print)
        changes["print"] = replace(
            settings.print, phases=settings.print.phases - blocked_print
        )

    if convert_overrides := _collect_overrides(
        settings.convert, _CONVERT_NO_PATH_FIELDS, need_file_opts
    ):
        changes["convert"] = replace(settings.convert, **convert_overrides)
    if write_overrides := _collect_overrides(
        settings.write, _WRITE_NO_PATH_FIELDS, need_file_opts
    ):
        changes["write"] = replace(settings.write, **write_overrides)

    return changes, need_file_opts


def post_process_set_for_path(
    settings: ComicboxSettings, path: str | Path | None, *, box: bool
) -> ComicboxSettings:
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
