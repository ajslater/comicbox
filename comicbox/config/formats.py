"""Transform config format keys to MetadataFormats."""

import contextlib
from collections.abc import Iterable, Mapping
from typing import Any

from confuse import Subview, exceptions
from loguru import logger


def _raw_or_empty(view: Subview) -> Iterable[Any]:
    """
    Return the view's raw Python value, or () when missing/None.

    Used in lieu of iterating Subviews directly (which only supports
    dict/list source values) so that user-supplied set/frozenset/tuple
    inputs survive compute_config.

    Mappings are rejected explicitly: dict/Mapping iteration yields keys,
    which would silently accept dict input on fields that should only
    take a non-mapping container of values. Strings are returned as-is
    (Iterable[str] yielding chars) — that's the existing print-field
    contract; other consumers either treat str as a one-char-iterable
    or check isinstance(..., str) themselves.
    """
    with contextlib.suppress(exceptions.NotFoundError):
        value = view.get()
        if isinstance(value, Mapping):
            reason = (
                f"{view.name} must be a non-mapping container "
                f"(set/frozenset/tuple/list), not a mapping"
            )
            raise exceptions.ConfigTypeError(reason)
        if not value:
            return ()
        if isinstance(value, Iterable):
            return value
    return ()


def _get_formats_from_keys(keys: frozenset[str], ignore_keys: frozenset[Any]) -> tuple:
    """Get sources from keys."""
    from comicbox.formats import MetadataFormats

    fmts = []
    for fmt in MetadataFormats:
        format_keys = fmt.value.config_keys
        if fmt.value.enabled and (not ignore_keys & format_keys and keys & format_keys):
            fmts.append(fmt)
        keys -= format_keys
        ignore_keys -= format_keys
    return fmts, keys


def _resolve_formats(
    config_view: Subview, label: str, *, ignore_view: Subview | None = None
) -> frozenset:
    """Resolve a set of config-key strings into a frozenset of MetadataFormats."""
    raw_keys = _raw_or_empty(config_view)
    keys = frozenset({str(k).strip() for k in raw_keys})

    ignore_keys: frozenset[Any] = frozenset()
    if ignore_view is not None:
        raw_ignore = _raw_or_empty(ignore_view)
        ignore_keys = frozenset({str(k).strip() for k in raw_ignore})

    fmts, keys = _get_formats_from_keys(keys, ignore_keys)

    # Report on invalid formats.
    if keys:
        plural = "s" if len(keys) > 1 else ""
        keys_str = ", ".join(sorted(keys))
        logger.warning(f"Action '{label}' received invalid format{plural}: {keys_str}")

    return frozenset(fmts)


def transform_keys_to_formats(config: Subview) -> None:
    """Transform schema config keys to format enums."""
    if config["write"]["delete_all_tags"].get(bool):
        config["read"]["formats"].set(frozenset())
        config["write"]["formats"].set(frozenset())
        config["convert"]["export_formats"].set(frozenset())
        return

    read_fmts = _resolve_formats(config["read"]["formats"], "read")
    read_except = config["read"]["except"].get()
    if read_except and (
        except_fmts := _resolve_formats(config["read"]["except"], "read-except")
    ):
        read_fmts -= except_fmts
    config["read"]["formats"].set(read_fmts)

    write_fmts = _resolve_formats(config["write"]["formats"], "write")
    config["write"]["formats"].set(write_fmts)

    export_fmts = _resolve_formats(
        config["convert"]["export_formats"], "convert.export_formats"
    )
    config["convert"]["export_formats"].set(export_fmts)
