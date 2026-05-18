"""Confuse config for comicbox."""

from __future__ import annotations

import os
from argparse import Namespace
from collections.abc import Callable, Iterable, Mapping
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
    CacheMode,
    ComicboxSettings,
    ComputeSettings,
    ConvertSettings,
    Effort,
    GeneralSettings,
    MatchMode,
    OnlineAuthSettings,
    OnlineCacheSettings,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceLimits,
    OnlineSourceTuning,
    OnlineTuningSettings,
    PrintSettings,
    Prompts,
    ReadSettings,
    WriteSettings,
)
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.formats.base.online.cli_overrides import CliOverrides
from comicbox.formats.base.online.credentials import resolve_credentials
from comicbox.formats.base.online.env import read_online_env
from comicbox.formats.sources import MetadataSources
from comicbox.identifiers import PARSE_COMICVINE_RE
from comicbox.version import PACKAGE_NAME

# ComicVine resource-type prefixes.
_CV_ISSUE_RESOURCE_TYPE = 4000
_CV_VOLUME_RESOURCE_TYPE = 4050

# Any non-Mapping container type — set/frozenset/tuple/list all pass.
_NON_MAPPING_TYPES = (set, frozenset, tuple, list)
_NON_MAPPING_CONTAINER = OneOf(_NON_MAPPING_TYPES)


_RATE_LIMIT_TEMPLATE = MappingTemplate(
    {
        "per_minute": Optional(Integer()),
        "per_day": Optional(Integer()),
        "per_second": Optional(Integer()),
        "per_hour": Optional(Integer()),
    }
)


_PER_SOURCE_TUNING_TEMPLATE = MappingTemplate(
    {
        "auto_threshold": Optional(Number()),
        "effort": Optional(String()),
        "min_confidence": Optional(Number()),
        "disambiguation_margin": Optional(Number()),
        "solo_threshold": Optional(Number()),
        "rate_limit": Optional(_RATE_LIMIT_TEMPLATE),
    }
)


_AUTH_SOURCE_TEMPLATE = MappingTemplate(
    {
        "user": Optional(str),
        "pass": Optional(str),
        "key": Optional(str),
        "url": Optional(str),
    }
)


_ONLINE_TEMPLATE = MappingTemplate(
    {
        "lookup": MappingTemplate(
            {
                "match": String(),
                "prompts": String(),
                "rematch": bool,
                "all_sources": bool,
            }
        ),
        "auth": MappingTemplate(
            {
                "metron": _AUTH_SOURCE_TEMPLATE,
                "comicvine": _AUTH_SOURCE_TEMPLATE,
            }
        ),
        "cache": MappingTemplate(
            {
                "mode": String(),
                "dir": Optional(OneOf((str, Path))),
                "ttl": String(),
            }
        ),
        "tuning": MappingTemplate(
            {
                "auto_threshold": Number(),
                "effort": String(),
                "retry_budget": Integer(),
                "per_source": Optional(dict),
            }
        ),
    }
)


_TEMPLATE = MappingTemplate(
    {
        PACKAGE_NAME: MappingTemplate(
            {
                "general": MappingTemplate(
                    {
                        "config": Optional(OneOf((str, Path))),
                        "recurse": bool,
                        "dry_run": bool,
                        "loglevel": OneOf((String(), Integer())),
                        "dest_path": OneOf((str, Path)),
                        "delete_keys": Optional(_NON_MAPPING_CONTAINER),
                        "delete_orig": bool,
                        "metadata": Optional(dict),
                        "metadata_cli": Optional(Sequence(str)),
                        "metadata_format": Optional(str),
                        "jobs": Integer(),
                        "tagger": Optional(str),
                        "theme": Optional(str),
                    }
                ),
                "read": MappingTemplate(
                    {
                        "formats": Optional(_NON_MAPPING_CONTAINER),
                        "except": Optional(_NON_MAPPING_CONTAINER),
                        "merge_order": Optional(_NON_MAPPING_CONTAINER),
                    }
                ),
                "write": MappingTemplate(
                    {
                        "formats": Optional(_NON_MAPPING_CONTAINER),
                        "replace": bool,
                        "stamp": bool,
                        "stamp_notes": bool,
                        "delete_all_tags": bool,
                    }
                ),
                "print": MappingTemplate(
                    {
                        "phases": Optional(OneOf((*_NON_MAPPING_TYPES, str))),
                        "validate": Optional(bool),
                    }
                ),
                "convert": MappingTemplate(
                    {
                        "cbz": Optional(bool),
                        "rename": Optional(bool),
                        "extract_pages_from": Optional(int),
                        "extract_pages_to": Optional(int),
                        "extract_covers": Optional(bool),
                        "import_paths": Optional(Sequence(OneOf((str, Path)))),
                        "export_formats": Optional(_NON_MAPPING_CONTAINER),
                        "pdf_pages": Choice(("", *PAGE_FORMAT_VALUES)),
                    }
                ),
                "compute": MappingTemplate(
                    {
                        "pages": bool,
                        "page_count": bool,
                    }
                ),
                "online": _ONLINE_TEMPLATE,
                "paths": Optional(OneOf((Sequence(OneOf((str, Path))), None))),
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
        try:
            return timedelta(seconds=int(raw))
        except ValueError:
            logger.warning(
                f"unparseable cache.ttl {raw!r}, defaulting to 7d "
                "(use forms like 7d, 24h, 60m, or 0)"
            )
            return timedelta(days=7)
    try:
        magnitude = int(raw[:-1])
    except ValueError:
        logger.warning(
            f"unparseable cache.ttl {raw!r}, defaulting to 7d "
            "(use forms like 7d, 24h, 60m, or 0)"
        )
        return timedelta(days=7)
    return timedelta(seconds=magnitude * _TTL_UNIT_SECONDS[suffix])


def _resolve_merge_order(
    raw: Any,
) -> tuple[MetadataSources, ...] | None:
    """Convert a list of source names → ordered tuple of `MetadataSources`."""
    if not raw:
        return None
    out: list[MetadataSources] = []
    seen: set[MetadataSources] = set()
    for name in raw:
        try:
            member = MetadataSources[str(name).upper()]
        except KeyError:
            logger.warning(f"read.merge_order: unknown source {name!r}, skipping")
            continue
        if member in seen:
            reason = f"read.merge_order: duplicate source {name!r}"
            raise ValueError(reason)
        seen.add(member)
        out.append(member)
    out.extend(member for member in MetadataSources if member not in seen)
    return tuple(out)


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value (order = priority)."""
    for v in values:
        if v is not None:
            return v
    return None


def _parse_match_value(raw: str) -> MatchMode:
    try:
        return MatchMode(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(m.value for m in MatchMode)
        reason = f"--match: unknown name {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_prompts_value(raw: str) -> Prompts:
    try:
        return Prompts(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(p.value for p in Prompts)
        reason = f"--prompts: unknown value {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_effort_value(raw: str) -> Effort:
    try:
        return Effort(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(e.value for e in Effort)
        reason = f"--effort: unknown name {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_cache_mode_value(raw: str) -> CacheMode:
    try:
        return CacheMode(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(c.value for c in CacheMode)
        reason = f"--cache: unknown value {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_explicit_id(source: str, raw: str) -> int:
    """Normalize the raw `--id` value into a numeric issue id."""
    raw = raw.strip()
    if source == "comicvine" and (m := PARSE_COMICVINE_RE.fullmatch(raw)):
        id_type = int(m.group("id_type"))
        if id_type != _CV_ISSUE_RESOURCE_TYPE:
            reason = (
                f"--id comicvine:{raw}: resource type {id_type} is not "
                f"supported (expected {_CV_ISSUE_RESOURCE_TYPE} = issue)"
            )
            raise ValueError(reason)
        return int(m.group("id_key"))
    try:
        return int(raw)
    except ValueError as exc:
        reason = f"--id: non-numeric id {raw!r} for {source}"
        raise ValueError(reason) from exc


def _parse_explicit_series_id(source: str, raw: str) -> int:
    """Normalize the raw `--series-id` value into a numeric series/volume id."""
    raw = raw.strip()
    if source == "comicvine" and (m := PARSE_COMICVINE_RE.fullmatch(raw)):
        id_type = int(m.group("id_type"))
        if id_type != _CV_VOLUME_RESOURCE_TYPE:
            reason = (
                f"--series-id comicvine:{raw}: resource type {id_type} is "
                f"not supported (expected {_CV_VOLUME_RESOURCE_TYPE} = volume)"
            )
            raise ValueError(reason)
        return int(m.group("id_key"))
    try:
        return int(raw)
    except ValueError as exc:
        reason = f"--series-id: non-numeric id {raw!r} for {source}"
        raise ValueError(reason) from exc


def _parse_db_id_list(
    raw_list: Iterable[str] | None,
    flag_name: str,
    parse_value: Callable[[str, str], int],
) -> dict[str, int]:
    """Parse a list of `DB:ID` strings."""
    out: dict[str, int] = {}
    for raw in raw_list or ():
        if ":" not in raw:
            reason = f"{flag_name} expects DB:ID, got {raw!r}"
            raise ValueError(reason)
        source, _, value = raw.partition(":")
        source = source.strip().lower()
        if source not in SOURCE_NAMES:
            reason = (
                f"{flag_name}: unknown source {source!r}; "
                f"known: {', '.join(SOURCE_NAMES)}"
            )
            raise ValueError(reason)
        out[source] = parse_value(source, value)
    return out


@dataclass(frozen=True, slots=True)
class _RuntimeOnlineInputs:
    """Bag of CLI-derived online inputs for `_build_online_settings`."""

    cli_overrides: CliOverrides | None = None
    enabled: bool = False
    sources: frozenset[str] | None = None
    ids: Mapping[str, int] = field(default_factory=dict)
    series_ids: Mapping[str, int] = field(default_factory=dict)
    cache_mode_cli: CacheMode | None = None


def _build_per_source_tuning(
    online_block: Any,
) -> dict[str, OnlineSourceTuning]:
    """Read `online.tuning.per_source.<name>.*` into `OnlineSourceTuning` objects."""
    raw: Any = getattr(online_block.tuning, "per_source", None)
    if not raw:
        return {}
    out: dict[str, OnlineSourceTuning] = {}
    for name, raw_block in dict(raw).items():
        if not isinstance(raw_block, Mapping):
            continue
        block: Mapping[str, Any] = raw_block
        rl_raw: Mapping[str, Any] = block.get("rate_limit") or {}
        limits = OnlineSourceLimits(
            per_minute=rl_raw.get("per_minute"),
            per_day=rl_raw.get("per_day"),
            per_second=rl_raw.get("per_second"),
            per_hour=rl_raw.get("per_hour"),
        )
        effort_raw = block.get("effort")
        out[str(name).lower()] = OnlineSourceTuning(
            auto_threshold=block.get("auto_threshold"),
            effort=_parse_effort_value(str(effort_raw)) if effort_raw else None,
            min_confidence=block.get("min_confidence"),
            disambiguation_margin=block.get("disambiguation_margin"),
            solo_threshold=block.get("solo_threshold"),
            rate_limit=limits,
        )
    return out


def _build_auth_settings(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    *,
    env: Mapping[str, str],
) -> OnlineAuthSettings:
    """Build per-source credentials from CLI + env + config + keyring."""
    config_creds: dict[str, dict[str, Any]] = {}
    auth_block: Any = getattr(online_block, "auth", None)
    for source in SOURCE_NAMES:
        block: Any = getattr(auth_block, source, None) if auth_block else None
        if block is None:
            continue
        config_creds[source] = {
            "user": getattr(block, "user", None),
            "pass": getattr(block, "pass", None),
            "key": getattr(block, "key", None),
            "url": getattr(block, "url", None),
        }

    resolved = resolve_credentials(
        config_creds=config_creds,
        cli_overrides=runtime.cli_overrides,
        env=env,
    )
    return OnlineAuthSettings(sources=resolved)


def _build_online_settings(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    *,
    cns: Namespace | None = None,
    env: Mapping[str, str] | None = None,
) -> OnlineSettings:
    """Build the nested `OnlineSettings` from confuse + env + CLI overrides."""
    if env is None:
        env = os.environ
    online_env = read_online_env(env)

    def _cli(field: str) -> Any:
        return getattr(cns, field, None) if cns is not None else None

    # Lookup
    match_raw = _coalesce(
        _cli("match"), online_env.get("match"), online_block.lookup.match
    )
    prompts_raw = _coalesce(
        _cli("prompts"), online_env.get("prompts"), online_block.lookup.prompts
    )
    rematch = bool(
        _coalesce(
            _cli("rematch"),
            online_env.get("rematch"),
            online_block.lookup.rematch,
        )
    )
    all_sources = bool(
        _coalesce(
            _cli("all_sources"),
            online_env.get("all_sources"),
            online_block.lookup.all_sources,
        )
    )
    match_mode = _parse_match_value(str(match_raw)) if match_raw else MatchMode.AUTO
    prompts_value = (
        _parse_prompts_value(str(prompts_raw)) if prompts_raw else Prompts.ASK
    )

    lookup = OnlineLookupSettings(
        enabled=runtime.enabled,
        sources=runtime.sources,
        ids=dict(runtime.ids),
        series_ids=dict(runtime.series_ids),
        match=match_mode,
        prompts=prompts_value,
        rematch=rematch,
        all_sources=all_sources,
    )

    # Auth
    auth = _build_auth_settings(online_block, runtime, env=env)

    # Cache
    cache_mode_raw = _coalesce(
        runtime.cache_mode_cli,
        online_env.get("cache"),
        online_block.cache.mode,
    )
    cache_mode = (
        cache_mode_raw
        if isinstance(cache_mode_raw, CacheMode)
        else _parse_cache_mode_value(str(cache_mode_raw))
    )
    cache_dir_raw = _coalesce(
        _cli("cache_dir"), online_env.get("cache_dir"), online_block.cache.dir
    )
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    cache_ttl_raw = _coalesce(
        _cli("cache_ttl"), online_env.get("cache_ttl"), online_block.cache.ttl
    )
    cache = OnlineCacheSettings(
        mode=cache_mode,
        dir=cache_dir,
        ttl=_parse_ttl(cache_ttl_raw),
    )

    # Tuning
    auto_threshold_raw = _coalesce(
        _cli("auto_threshold"),
        online_env.get("auto_threshold"),
        online_block.tuning.auto_threshold,
    )
    auto_threshold = (
        float(auto_threshold_raw) if auto_threshold_raw is not None else 0.95
    )
    effort_raw = _coalesce(
        _cli("effort"), online_env.get("effort"), online_block.tuning.effort
    )
    effort_value = (
        _parse_effort_value(str(effort_raw)) if effort_raw else Effort.BALANCED
    )
    retry_budget = int(
        _coalesce(online_env.get("retry_budget"), online_block.tuning.retry_budget, 5)
    )
    per_source = _build_per_source_tuning(online_block)
    tuning = OnlineTuningSettings(
        auto_threshold=auto_threshold,
        effort=effort_value,
        retry_budget=retry_budget,
        per_source=per_source,
    )

    return OnlineSettings(lookup=lookup, auth=auth, cache=cache, tuning=tuning)


def _runtime_online_inputs(
    args: Namespace | Mapping | None,
) -> _RuntimeOnlineInputs:
    """Extract online-related runtime values from CLI args (Namespace only)."""
    if not isinstance(args, Namespace):
        return _RuntimeOnlineInputs()

    cns: Any = getattr(args, "comicbox", args)
    if not isinstance(cns, Namespace):
        cns = args

    online_arg: Any = getattr(cns, "online_sources", None)

    ids = _parse_db_id_list(
        getattr(cns, "explicit_ids", None), "--id", _parse_explicit_id
    )
    series_ids = _parse_db_id_list(
        getattr(cns, "explicit_series_ids", None),
        "--series-id",
        _parse_explicit_series_id,
    )

    explicit_id_sources = frozenset(ids.keys()) | frozenset(series_ids.keys())

    selected: frozenset[str] | None
    if online_arg is None:
        if explicit_id_sources:
            runtime_enabled = True
            selected = explicit_id_sources
        else:
            runtime_enabled = False
            selected = None
    else:
        runtime_enabled = True
        normalized = frozenset(
            str(s).strip().lower() for s in online_arg if str(s).strip()
        )
        if not normalized or "all" in normalized:
            selected = None
        else:
            selected = normalized | explicit_id_sources

    cli_overrides = CliOverrides.from_auth_list(getattr(cns, "auth", None) or ())

    cache_cli = getattr(cns, "cache", None)
    cache_mode_cli = _parse_cache_mode_value(str(cache_cli)) if cache_cli else None

    return _RuntimeOnlineInputs(
        cli_overrides=cli_overrides,
        enabled=runtime_enabled,
        sources=selected,
        ids=ids,
        series_ids=series_ids,
        cache_mode_cli=cache_mode_cli,
    )


def _build_settings(
    ad: Any,
    args: Namespace | Mapping | None = None,
) -> ComicboxSettings:
    """Convert a validated, computed confuse AttrDict into a ComicboxSettings dataclass."""
    inner: Any = ad.comicbox
    computed: Any = inner.computed

    runtime_inputs = _runtime_online_inputs(args)

    cns_for_overrides: Namespace | None = None
    if isinstance(args, Namespace):
        candidate = getattr(args, "comicbox", args)
        cns_for_overrides = candidate if isinstance(candidate, Namespace) else args

    online = _build_online_settings(inner.online, runtime_inputs, cns=cns_for_overrides)

    general_block = inner.general
    metadata_cli = general_block.metadata_cli
    general = GeneralSettings(
        config=general_block.config,
        recurse=bool(general_block.recurse),
        dry_run=bool(general_block.dry_run),
        loglevel=general_block.loglevel,
        dest_path=general_block.dest_path,
        delete_keys=frozenset(general_block.delete_keys or ()),
        delete_orig=bool(general_block.delete_orig),
        metadata=general_block.metadata,
        metadata_cli=tuple(metadata_cli) if metadata_cli else None,
        metadata_format=general_block.metadata_format,
        jobs=max(1, int(general_block.jobs)),
        tagger=general_block.tagger,
        theme=general_block.theme,
    )

    read_block = inner.read
    read_settings = ReadSettings(
        formats=frozenset(read_block.formats or ()),
        except_formats=(
            frozenset(getattr(read_block, "except"))
            if getattr(read_block, "except", None)
            else None
        ),
        merge_order=_resolve_merge_order(read_block.merge_order),
    )

    write_block = inner.write
    write_settings = WriteSettings(
        formats=frozenset(write_block.formats or ()),
        replace=bool(write_block.replace),
        stamp=bool(write_block.stamp),
        stamp_notes=bool(write_block.stamp_notes),
        delete_all_tags=bool(write_block.delete_all_tags),
    )

    print_block = inner.print
    print_settings = PrintSettings(
        phases=frozenset(print_block.phases or ()),
        validate=bool(print_block.validate),
    )

    convert_block = inner.convert
    convert_settings = ConvertSettings(
        cbz=convert_block.cbz,
        rename=convert_block.rename,
        extract_pages_from=convert_block.extract_pages_from,
        extract_pages_to=convert_block.extract_pages_to,
        extract_covers=convert_block.extract_covers,
        import_paths=expand_glob_paths(convert_block.import_paths),
        export_formats=frozenset(convert_block.export_formats or ()),
        pdf_pages=convert_block.pdf_pages,
    )

    compute_block = inner.compute
    compute_settings = ComputeSettings(
        pages=bool(compute_block.pages),
        page_count=bool(compute_block.page_count),
    )

    return ComicboxSettings(
        general=general,
        read=read_settings,
        write=write_settings,
        print=print_settings,
        convert=convert_settings,
        compute=compute_settings,
        online=online,
        paths=tuple(inner.paths or ()),
        all_write_formats=frozenset(computed.all_write_formats),
        read_filename_formats=frozenset(computed.read_filename_formats),
        read_file_formats=frozenset(computed.read_file_formats),
        read_metadata_lower_filenames=frozenset(computed.read_metadata_lower_filenames),
        is_read_comments=bool(computed.is_read_comments),
        is_skip_computed_from_tags=bool(computed.is_skip_computed_from_tags),
    )


def get_config(
    args: Namespace | Mapping | ComicboxSettings | None = None,
    *,
    modname: str = PACKAGE_NAME,
    path: str | Path | None = None,
    box: bool = False,
) -> ComicboxSettings:
    """Get the config dict, layering env and args over defaults."""
    if isinstance(args, ComicboxSettings):
        return post_process_set_for_path(args, path, box=box)
    if isinstance(args, Mapping):
        args = dict(args)

    config = Configuration(PACKAGE_NAME, modname=modname, read=False)
    read_config_sources(config, args)

    config_program = config[PACKAGE_NAME]
    compute_config(config_program)

    ad = config.get(_TEMPLATE)
    settings = _build_settings(ad, args=args)
    return post_process_set_for_path(settings, path, box=box)
