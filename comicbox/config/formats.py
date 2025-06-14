"""Transform config format keys to MetadataFormats."""

from confuse import Subview
from loguru import logger

from comicbox.formats import MetadataFormats


def _get_formats_from_keys(keys, ignore_keys):
    """Get sources from keys."""
    fmts = []
    for fmt in MetadataFormats:
        format_keys = fmt.value.config_keys
        if fmt.value.enabled and (not ignore_keys & format_keys and keys & format_keys):
            fmts.append(fmt)
        keys -= format_keys
        ignore_keys -= format_keys
    return fmts, keys


def _get_config_formats_from_keys(config, key):
    """Return a set of schemas from a sequence of config keys."""
    # Keys to set
    keys = config[key] or ()
    keys = frozenset({str(key).strip() for key in keys})

    # Ignore list to set
    attr = f"{key}_ignore"
    ignore_list = getattr(config, attr, ())
    ignore_keys = frozenset({str(key).strip() for key in ignore_list})
    fmts, keys = _get_formats_from_keys(keys, ignore_keys)

    # Report on invalid formats.
    if keys:
        plural = "s" if len(keys) > 1 else ""
        keys_str = ", ".join(sorted(keys))
        logger.warning(f"Action '{key}' received invalid format{plural}: {keys_str}")

    return frozenset(fmts)


def transform_keys_to_formats(config: Subview):
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
