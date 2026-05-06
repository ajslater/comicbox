"""Confuse config for comicbox."""

import os
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from confuse import Configuration
from confuse.templates import (
    Choice,
    Integer,
    MappingTemplate,
    Number,
    OneOf,
    Optional,
    Sequence,
    String,
)
from loguru import logger

from comicbox._pdf import PAGE_FORMAT_VALUES
from comicbox.config.computed import compute_config
from comicbox.config.paths import (
    expand_glob_paths,
    post_process_set_for_path,
)
from comicbox.config.read import read_config_sources
from comicbox.config.settings import (
    ComicboxSettings,
    OnlineSettings,
)
from comicbox.online import SOURCE_NAMES
from comicbox.online.cli_overrides import CliOverrides
from comicbox.online.credentials import resolve_credentials
from comicbox.online.env import read_policy_env
from comicbox.sources import MetadataSources
from comicbox.version import PACKAGE_NAME

# Any non-Mapping container type — set/frozenset/tuple/list all pass.
# `_build_settings` normalizes the validated value into the right immutable
# type for the dataclass (frozenset for set-like fields, tuple for sequences),
# so the template intentionally doesn't pin element types here.
_NON_MAPPING_TYPES = (set, frozenset, tuple, list)
_NON_MAPPING_CONTAINER = OneOf(_NON_MAPPING_TYPES)


_ONLINE_SOURCE_TEMPLATE = MappingTemplate(
    {
        "api_key": Optional(str),
        "username": Optional(str),
        "password": Optional(str),
        "url": Optional(str),
    }
)

_ONLINE_TEMPLATE = MappingTemplate(
    {
        "confidence_threshold": Number(),
        "skip_multiple": bool,
        "accept_only": bool,
        "ignore_existing": bool,
        "cache_enabled": bool,
        "cache_dir": Optional(OneOf((str, Path))),
        "cache_ttl": String(),
        "refresh_cache": bool,
        "retry_budget": Integer(),
        "metron": _ONLINE_SOURCE_TEMPLATE,
        "comicvine": _ONLINE_SOURCE_TEMPLATE,
    }
)


_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                # Options
                "compute_pages": bool,
                "compute_page_count": bool,
                "config": Optional(OneOf((str, Path))),
                "delete_all_tags": bool,
                "delete_keys": Optional(_NON_MAPPING_CONTAINER),
                "delete_orig": bool,
                "dest_path": OneOf((str, Path)),
                "dry_run": bool,
                "loglevel": OneOf((String(), Integer())),
                "metadata": Optional(dict),
                "metadata_format": Optional(str),
                "metadata_cli": Optional(Sequence(str)),
                "pdf_page_format": Choice(("", *PAGE_FORMAT_VALUES)),
                "read": Optional(_NON_MAPPING_CONTAINER),
                "read_ignore": Optional(_NON_MAPPING_CONTAINER),
                "recurse": bool,
                "replace_metadata": bool,
                "stamp": bool,
                "stamp_notes": bool,
                "tagger": Optional(str),
                "theme": Optional(str),
                # Actions
                "cbz": Optional(bool),
                "covers": Optional(bool),
                "export": Optional(_NON_MAPPING_CONTAINER),
                "import_paths": Optional(Sequence(OneOf((str, Path)))),
                "index_from": Optional(int),
                "index_to": Optional(int),
                "print": Optional(OneOf((*_NON_MAPPING_TYPES, str))),
                "rename": Optional(bool),
                "validate": Optional(bool),
                "write": Optional(_NON_MAPPING_CONTAINER),
                # Targets
                "paths": Optional(OneOf((Sequence(OneOf((str, Path))), None))),
                # Merge precedence (None = MetadataSources enum order).
                "merge_order": Optional(_NON_MAPPING_CONTAINER),
                # Online metadata tagging.
                "online": _ONLINE_TEMPLATE,
                # Computed
                "computed": Optional(
                    MappingTemplate(
                        {
                            "all_write_formats": frozenset,
                            "read_filename_formats": frozenset,
                            "read_file_formats": frozenset,
                            "read_metadata_lower_filenames": frozenset,
                            "is_read_comments": bool,
                            "is_skip_computed_from_tags": bool,
                        }
                    )
                ),
            }
        )
    }
)


_TTL_UNIT_SECONDS: Mapping[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def _parse_ttl(raw: str | None) -> timedelta:
    """Parse a simple duration string like '7d', '24h', '60m', '0' → timedelta."""
    if raw is None:
        return timedelta(days=7)
    raw = raw.strip().lower()
    if not raw or raw == "0":
        return timedelta(0)
    suffix = raw[-1]
    if suffix not in _TTL_UNIT_SECONDS:
        # Treat a bare number as seconds.
        try:
            return timedelta(seconds=int(raw))
        except ValueError:
            msg = f"unparseable cache_ttl {raw!r}, defaulting to 7d (use forms like 7d, 24h, 60m, or 0)"
            logger.warning(msg)
            return timedelta(days=7)
    try:
        magnitude = int(raw[:-1])
    except ValueError:
        msg = f"unparseable cache_ttl {raw!r}, defaulting to 7d (use forms like 7d, 24h, 60m, or 0)"
        logger.warning(msg)
        return timedelta(days=7)
    return timedelta(seconds=magnitude * _TTL_UNIT_SECONDS[suffix])


def _resolve_merge_order(
    raw: Any,
) -> tuple[MetadataSources, ...] | None:
    """
    Convert a config list of source names → ordered tuple of `MetadataSources`.

    None or empty → returns None (use enum order). Missing members are
    silently appended at the end (preserves user configs across enum
    additions). Duplicates raise.
    """
    if not raw:
        return None
    out: list[MetadataSources] = []
    seen: set[MetadataSources] = set()
    for name in raw:
        try:
            member = MetadataSources[str(name).upper()]
        except KeyError:
            logger.warning(f"merge_order: unknown source {name!r}, skipping")
            continue
        if member in seen:
            reason = f"merge_order: duplicate source {name!r}"
            raise ValueError(reason)
        seen.add(member)
        out.append(member)
    # Append any missing members at the end so adding new sources later
    # doesn't break existing user configs.
    out.extend(member for member in MetadataSources if member not in seen)
    return tuple(out)


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value (order = priority)."""
    for v in values:
        if v is not None:
            return v
    return None


@dataclass(frozen=True, slots=True)
class _RuntimeOnlineInputs:
    """Bag of CLI-derived online inputs for `_build_online_settings`."""

    cli_overrides: CliOverrides | None = None
    enabled: bool = False
    selected_sources: frozenset[str] | None = None
    explicit_ids: Mapping[str, int] = field(default_factory=dict)
    no_cache: bool = False
    refresh_cache: bool = False


def _build_online_settings(
    inner: Any,
    runtime: _RuntimeOnlineInputs,
    *,
    cns: Namespace | None = None,
    env: Mapping[str, str] | None = None,
) -> OnlineSettings:
    """
    Build the nested `OnlineSettings` from confuse + env + CLI overrides.

    Priority (per field): CLI flag > env var > confuse-resolved config
    (which already merged file + system defaults). The credential layer
    additionally falls back to keyring inside `resolve_credentials`.
    """
    online: Any = inner.online

    if env is None:
        env = os.environ
    policy_env = read_policy_env(env)

    def _cli(field: str) -> Any:
        return getattr(cns, field, None) if cns is not None else None

    accept_only = bool(
        _coalesce(
            _cli("accept_only"), policy_env.get("accept_only"), online.accept_only
        )
    )
    skip_multiple = bool(
        _coalesce(
            _cli("skip_multiple"),
            policy_env.get("skip_multiple"),
            online.skip_multiple,
        )
    )
    ignore_existing = bool(
        _coalesce(
            _cli("ignore_existing"),
            policy_env.get("ignore_existing"),
            online.ignore_existing,
        )
    )
    confidence_threshold = float(
        _coalesce(
            _cli("confidence_threshold"),
            policy_env.get("confidence_threshold"),
            online.confidence_threshold,
        )
    )

    cache_enabled = bool(
        _coalesce(policy_env.get("cache_enabled"), online.cache_enabled)
    )
    if runtime.no_cache:
        cache_enabled = False

    refresh_cache = bool(
        _coalesce(policy_env.get("refresh_cache"), online.refresh_cache)
    )
    if runtime.refresh_cache:
        refresh_cache = True

    cache_dir_raw = _coalesce(
        _cli("cache_dir"), policy_env.get("cache_dir"), online.cache_dir
    )
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None

    cache_ttl_raw = _coalesce(
        _cli("cache_ttl"), policy_env.get("cache_ttl"), online.cache_ttl
    )

    retry_budget = int(_coalesce(policy_env.get("retry_budget"), online.retry_budget))

    config_creds: dict[str, dict[str, Any]] = {}
    for source in SOURCE_NAMES:
        block: Any = getattr(online, source, None)
        if block is None:
            continue
        config_creds[source] = {
            "api_key": getattr(block, "api_key", None),
            "username": getattr(block, "username", None),
            "password": getattr(block, "password", None),
            "url": getattr(block, "url", None),
        }

    sources_creds = resolve_credentials(
        config_creds=config_creds,
        cli_overrides=runtime.cli_overrides,
        env=env,
    )

    return OnlineSettings(
        enabled=runtime.enabled,
        selected_sources=runtime.selected_sources,
        explicit_ids=dict(runtime.explicit_ids),
        confidence_threshold=confidence_threshold,
        skip_multiple=skip_multiple,
        accept_only=accept_only,
        ignore_existing=ignore_existing,
        cache_enabled=cache_enabled,
        cache_dir=cache_dir,
        cache_ttl=_parse_ttl(cache_ttl_raw),
        refresh_cache=refresh_cache,
        retry_budget=retry_budget,
        sources=sources_creds,
    )


def _runtime_online_inputs(
    args: Namespace | Mapping | None,
) -> _RuntimeOnlineInputs:
    """Extract online-related runtime values from CLI args (Namespace only)."""
    if not isinstance(args, Namespace):
        return _RuntimeOnlineInputs()

    # CLI flow wraps the parsed namespace as Namespace(comicbox=cns); the new
    # online flags live on cns. Programmatic callers may pass cns directly.
    cns: Any = getattr(args, "comicbox", args)
    if not isinstance(cns, Namespace):
        cns = args

    online_arg: Any = getattr(cns, "online_sources", None)
    if online_arg is None:
        runtime_enabled = False
        selected: frozenset[str] | None = None
    else:
        runtime_enabled = True
        normalized = frozenset(
            str(s).strip().lower() for s in online_arg if str(s).strip()
        )
        # `all` (or an empty list) is the "every configured source" sentinel.
        selected = None if not normalized or "all" in normalized else normalized

    explicit_raw: list[str] = list(getattr(cns, "explicit_ids", None) or ())
    explicit_ids: dict[str, int] = {}
    for raw in explicit_raw:
        if ":" not in raw:
            reason = f"--id expects DB:ID, got {raw!r}"
            raise ValueError(reason)
        source, _, value = raw.partition(":")
        source = source.strip().lower()
        if source not in SOURCE_NAMES:
            reason = (
                f"--id: unknown source {source!r}; known: {', '.join(SOURCE_NAMES)}"
            )
            raise ValueError(reason)
        try:
            issue_id = int(value)
        except ValueError as exc:
            reason = f"--id: non-numeric id {value!r} for {source}"
            raise ValueError(reason) from exc
        explicit_ids[source] = issue_id

    cli_overrides = CliOverrides.from_cli(
        api_keys=getattr(cns, "api_keys", None) or (),
        api_users=getattr(cns, "api_users", None) or (),
        api_passwords=getattr(cns, "api_passwords", None) or (),
        api_urls=getattr(cns, "api_urls", None) or (),
    )

    no_cache = bool(getattr(cns, "no_cache", False))
    refresh_cache = bool(getattr(cns, "refresh_cache", False))

    return _RuntimeOnlineInputs(
        cli_overrides=cli_overrides,
        enabled=runtime_enabled,
        selected_sources=selected,
        explicit_ids=explicit_ids,
        no_cache=no_cache,
        refresh_cache=refresh_cache,
    )


def _build_settings(
    ad: Any,
    args: Namespace | Mapping | None = None,
) -> ComicboxSettings:
    """Convert a validated, computed confuse AttrDict into a ComicboxSettings dataclass."""
    inner: Any = ad.comicbox
    metadata_cli = inner.metadata_cli
    computed: Any = inner.computed

    runtime_inputs = _runtime_online_inputs(args)

    cns_for_overrides: Namespace | None = None
    if isinstance(args, Namespace):
        candidate = getattr(args, "comicbox", args)
        cns_for_overrides = candidate if isinstance(candidate, Namespace) else args

    online = _build_online_settings(
        inner,
        runtime_inputs,
        cns=cns_for_overrides,
    )

    return ComicboxSettings(
        # Options
        compute_pages=bool(inner.compute_pages),
        compute_page_count=bool(inner.compute_page_count),
        config=inner.config,
        delete_all_tags=bool(inner.delete_all_tags),
        delete_keys=frozenset(inner.delete_keys or ()),
        delete_orig=bool(inner.delete_orig),
        dest_path=inner.dest_path,
        dry_run=bool(inner.dry_run),
        loglevel=inner.loglevel,
        metadata=inner.metadata,
        metadata_format=inner.metadata_format,
        metadata_cli=tuple(metadata_cli) if metadata_cli else None,
        pdf_page_format=inner.pdf_page_format,
        read=frozenset(inner.read or ()),
        read_ignore=frozenset(inner.read_ignore) if inner.read_ignore else None,
        recurse=bool(inner.recurse),
        replace_metadata=bool(inner.replace_metadata),
        stamp=bool(inner.stamp),
        stamp_notes=bool(inner.stamp_notes),
        tagger=inner.tagger,
        theme=inner.theme,
        # Actions
        cbz=inner.cbz,
        covers=inner.covers,
        export=frozenset(inner.export or ()),
        import_paths=expand_glob_paths(inner.import_paths),
        index_from=inner.index_from,
        index_to=inner.index_to,
        print=frozenset(inner.print or ()),
        rename=inner.rename,
        validate=inner.validate,
        write=frozenset(inner.write or ()),
        # Targets
        paths=tuple(inner.paths or ()),
        # Computed
        all_write_formats=frozenset(computed.all_write_formats),
        read_filename_formats=frozenset(computed.read_filename_formats),
        read_file_formats=frozenset(computed.read_file_formats),
        read_metadata_lower_filenames=frozenset(computed.read_metadata_lower_filenames),
        is_read_comments=bool(computed.is_read_comments),
        is_skip_computed_from_tags=bool(computed.is_skip_computed_from_tags),
        # Merge ordering
        merge_order=_resolve_merge_order(inner.merge_order),
        # Online tagging
        online=online,
    )


def get_config(
    args: Namespace | Mapping | ComicboxSettings | None = None,
    *,
    modname: str = PACKAGE_NAME,
    path: str | Path | None = None,
    box: bool = False,
) -> ComicboxSettings:
    """
    Get the config dict, layering env and args over defaults.

    Setting the box arg to True reconfigures attributes based on path or no path.
    """
    if isinstance(args, ComicboxSettings):
        # Already a config
        return post_process_set_for_path(args, path, box=box)
    if isinstance(args, Mapping):
        args = dict(args)

    # Read Sources
    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    read_config_sources(config, args)

    # Compute
    config_program = config[PACKAGE_NAME]
    compute_config(config_program)

    ad = config.get(_TEMPLATE)
    settings = _build_settings(ad, args=args)
    return post_process_set_for_path(settings, path, box=box)
