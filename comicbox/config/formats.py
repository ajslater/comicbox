"""Transform config format keys to MetadataFormats."""

import contextlib
from collections.abc import Iterable, Mapping
from typing import Any

from confuse import Subview, exceptions
from loguru import logger

from comicbox.formats import MetadataFormats


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
    fmts = []
    for fmt in MetadataFormats:
        format_keys = fmt.value.config_keys
        if fmt.value.enabled and (not ignore_keys & format_keys and keys & format_keys):
            fmts.append(fmt)
        keys -= format_keys
        ignore_keys -= format_keys
    return fmts, keys


def _get_config_formats_from_keys(config: Subview, key: str) -> frozenset:
    """Return a set of schemas from a sequence of config keys."""
    # Keys to set — pull raw value to support set/frozenset/tuple/list inputs.
    raw_keys = _raw_or_empty(config[key])
    keys = frozenset({str(k).strip() for k in raw_keys})

    # Ignore list to set
    attr = f"{key}_ignore"
    ignore_list = getattr(config, attr, ())
    ignore_keys = frozenset({str(k).strip() for k in ignore_list})
    fmts, keys = _get_formats_from_keys(keys, ignore_keys)

    # Report on invalid formats.
    if keys:
        plural = "s" if len(keys) > 1 else ""
        keys_str = ", ".join(sorted(keys))
        logger.warning(f"Action '{key}' received invalid format{plural}: {keys_str}")

    return frozenset(fmts)


def transform_keys_to_formats(config: Subview) -> None:
    """Transform schema config keys to format enums."""
    if config["delete_all_tags"].get(bool):
        config["read"].set(frozenset())
        config["write"].set(frozenset())
        config["export"].set(frozenset())
    else:
        read_fmts = _get_config_formats_from_keys(config, "read")
        read_ignore = config["read_ignore"].get()
        if read_ignore and (
            read_ignore_fmts := _get_config_formats_from_keys(config, "read_ignore")
        ):
            read_fmts -= read_ignore_fmts
        config["read"].set(read_fmts)
        write_fmts = _get_config_formats_from_keys(config, "write")
        config["write"].set(write_fmts)
        export_fmts = _get_config_formats_from_keys(config, "export")
        config["export"] = export_fmts
