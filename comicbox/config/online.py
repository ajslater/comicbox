"""
Online (tagging) settings assembly.

Precedence for the online block (CLI > env > config file) is hand-rolled
here instead of being layered through confuse because:

- Parse failures must raise typed ``ValueError``s with flag-specific
  messages (``--match: unknown name ...``); confuse templates would
  surface generic validation errors instead.
- The ``--id``/``--series-id`` maps and the per-source auth and tuning
  shapes are keyed by dynamic source names, which confuse's fixed
  ``MappingTemplate``s can't express.

Keep the env-var knobs read here in sync with
``comicbox.formats.base.online.env.read_online_env``.
"""

from __future__ import annotations

import os
from argparse import Namespace
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger

from comicbox.config.settings import (
    CacheMode,
    Effort,
    MatchMode,
    OnlineAuthSettings,
    OnlineCacheSettings,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceLimits,
    OnlineSourceTuning,
    OnlineTuningSettings,
    Prompts,
)
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.formats.base.online.cli_overrides import CliOverrides
from comicbox.formats.base.online.credentials import resolve_credentials
from comicbox.formats.base.online.env import read_online_env
from comicbox.identifiers import PARSE_COMICVINE_RE

# ComicVine resource-type prefixes.
_CV_ISSUE_RESOURCE_TYPE = 4000
_CV_VOLUME_RESOURCE_TYPE = 4050

_TTL_UNIT_SECONDS: Mapping[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}

_EnumT = TypeVar("_EnumT", bound=Enum)


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value (order = priority)."""
    for v in values:
        if v is not None:
            return v
    return None


def _parse_enum(
    enum_cls: type[_EnumT], flag: str, raw: str, *, noun: str = "name"
) -> _EnumT:
    """Parse a lowercased string into an enum member, raising a flag-tagged error."""
    try:
        return enum_cls(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(member.value for member in enum_cls)
        reason = f"{flag}: unknown {noun} {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_ttl(raw: str | None) -> timedelta:
    """Parse a simple duration string like '7d', '24h', '60m', '0' → timedelta."""
    if raw is None:
        return timedelta(days=7)
    raw = raw.strip().lower()
    if not raw or raw == "0":
        return timedelta(0)
    suffix = raw[-1]
    try:
        if suffix in _TTL_UNIT_SECONDS:
            return timedelta(seconds=int(raw[:-1]) * _TTL_UNIT_SECONDS[suffix])
        return timedelta(seconds=int(raw))
    except ValueError:
        logger.warning(
            f"unparseable cache.ttl {raw!r}, defaulting to 7d "
            "(use forms like 7d, 24h, 60m, or 0)"
        )
        return timedelta(days=7)


def _parse_explicit_db_id(
    source: str,
    raw: str,
    *,
    flag: str,
    cv_resource_type: int,
    cv_resource_name: str,
) -> int:
    """Normalize a raw `--id`/`--series-id` value into a numeric id."""
    raw = raw.strip()
    if source == "comicvine" and (m := PARSE_COMICVINE_RE.fullmatch(raw)):
        id_type = int(m.group("id_type"))
        if id_type != cv_resource_type:
            reason = (
                f"{flag} comicvine:{raw}: resource type {id_type} is not "
                f"supported (expected {cv_resource_type} = {cv_resource_name})"
            )
            raise ValueError(reason)
        return int(m.group("id_key"))
    try:
        return int(raw)
    except ValueError as exc:
        reason = f"{flag}: non-numeric id {raw!r} for {source}"
        raise ValueError(reason) from exc


_parse_explicit_id = partial(
    _parse_explicit_db_id,
    flag="--id",
    cv_resource_type=_CV_ISSUE_RESOURCE_TYPE,
    cv_resource_name="issue",
)
_parse_explicit_series_id = partial(
    _parse_explicit_db_id,
    flag="--series-id",
    cv_resource_type=_CV_VOLUME_RESOURCE_TYPE,
    cv_resource_name="volume",
)


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
            effort=_parse_enum(Effort, "--effort", str(effort_raw))
            if effort_raw
            else None,
            min_confidence=block.get("min_confidence"),
            disambiguation_margin=block.get("disambiguation_margin"),
            solo_threshold=block.get("solo_threshold"),
            rate_limit=limits,
        )
    return out


def _build_lookup(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    online_env: Mapping[str, Any],
    cli: Callable[[str], Any],
) -> OnlineLookupSettings:
    """Build `OnlineLookupSettings` from CLI > env > config."""
    match_raw = _coalesce(
        cli("match"), online_env.get("match"), online_block.lookup.match
    )
    prompts_raw = _coalesce(
        cli("prompts"), online_env.get("prompts"), online_block.lookup.prompts
    )
    rematch = bool(
        _coalesce(
            cli("rematch"),
            online_env.get("rematch"),
            online_block.lookup.rematch,
        )
    )
    all_sources = bool(
        _coalesce(
            cli("all_sources"),
            online_env.get("all_sources"),
            online_block.lookup.all_sources,
        )
    )
    match_mode = (
        _parse_enum(MatchMode, "--match", str(match_raw))
        if match_raw
        else MatchMode.AUTO
    )
    prompts_value = (
        _parse_enum(Prompts, "--prompts", str(prompts_raw), noun="value")
        if prompts_raw
        else Prompts.ASK
    )

    return OnlineLookupSettings(
        enabled=runtime.enabled,
        sources=runtime.sources,
        ids=dict(runtime.ids),
        series_ids=dict(runtime.series_ids),
        match=match_mode,
        prompts=prompts_value,
        rematch=rematch,
        all_sources=all_sources,
    )


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


def _build_cache(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    online_env: Mapping[str, Any],
    cli: Callable[[str], Any],
) -> OnlineCacheSettings:
    """Build `OnlineCacheSettings` from CLI > env > config."""
    cache_mode_raw = _coalesce(
        runtime.cache_mode_cli,
        online_env.get("cache"),
        online_block.cache.mode,
    )
    cache_mode = (
        cache_mode_raw
        if isinstance(cache_mode_raw, CacheMode)
        else _parse_enum(CacheMode, "--cache", str(cache_mode_raw), noun="value")
    )
    cache_dir_raw = _coalesce(
        cli("cache_dir"), online_env.get("cache_dir"), online_block.cache.dir
    )
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    cache_ttl_raw = _coalesce(
        cli("cache_ttl"), online_env.get("cache_ttl"), online_block.cache.ttl
    )
    return OnlineCacheSettings(
        mode=cache_mode,
        dir=cache_dir,
        ttl=_parse_ttl(cache_ttl_raw),
    )


def _build_tuning(
    online_block: Any,
    online_env: Mapping[str, Any],
    cli: Callable[[str], Any],
) -> OnlineTuningSettings:
    """Build `OnlineTuningSettings` from CLI > env > config."""
    auto_threshold_raw = _coalesce(
        cli("auto_threshold"),
        online_env.get("auto_threshold"),
        online_block.tuning.auto_threshold,
    )
    auto_threshold = (
        float(auto_threshold_raw) if auto_threshold_raw is not None else 0.95
    )
    effort_raw = _coalesce(
        cli("effort"), online_env.get("effort"), online_block.tuning.effort
    )
    effort_value = (
        _parse_enum(Effort, "--effort", str(effort_raw))
        if effort_raw
        else Effort.BALANCED
    )
    retry_budget = int(
        _coalesce(online_env.get("retry_budget"), online_block.tuning.retry_budget, 5)
    )
    per_source = _build_per_source_tuning(online_block)
    return OnlineTuningSettings(
        auto_threshold=auto_threshold,
        effort=effort_value,
        retry_budget=retry_budget,
        per_source=per_source,
    )


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

    return OnlineSettings(
        lookup=_build_lookup(online_block, runtime, online_env, _cli),
        auth=_build_auth_settings(online_block, runtime, env=env),
        cache=_build_cache(online_block, runtime, online_env, _cli),
        tuning=_build_tuning(online_block, online_env, _cli),
    )


def _resolve_runtime_sources(
    online_arg: Any, explicit_id_sources: frozenset[str]
) -> tuple[bool, frozenset[str] | None]:
    """Decide (enabled, selected) from --online-sources + explicit-id presence."""
    if online_arg is None:
        if explicit_id_sources:
            return True, explicit_id_sources
        return False, None
    normalized = frozenset(str(s).strip().lower() for s in online_arg if str(s).strip())
    if not normalized or "all" in normalized:
        return True, None
    return True, normalized | explicit_id_sources


def _runtime_online_inputs(
    args: Namespace | Mapping | None,
) -> _RuntimeOnlineInputs:
    """Extract online-related runtime values from CLI args (Namespace only)."""
    if not isinstance(args, Namespace):
        return _RuntimeOnlineInputs()

    cns: Any = getattr(args, "comicbox", args)
    if not isinstance(cns, Namespace):
        cns = args

    ids = _parse_db_id_list(
        getattr(cns, "explicit_ids", None), "--id", _parse_explicit_id
    )
    series_ids = _parse_db_id_list(
        getattr(cns, "explicit_series_ids", None),
        "--series-id",
        _parse_explicit_series_id,
    )
    explicit_id_sources = frozenset(ids.keys()) | frozenset(series_ids.keys())
    runtime_enabled, selected = _resolve_runtime_sources(
        getattr(cns, "online_sources", None), explicit_id_sources
    )

    cli_overrides = CliOverrides.from_auth_list(getattr(cns, "auth", None) or ())
    cache_cli = getattr(cns, "cache", None)
    cache_mode_cli = (
        _parse_enum(CacheMode, "--cache", str(cache_cli), noun="value")
        if cache_cli
        else None
    )

    return _RuntimeOnlineInputs(
        cli_overrides=cli_overrides,
        enabled=runtime_enabled,
        sources=selected,
        ids=ids,
        series_ids=series_ids,
        cache_mode_cli=cache_mode_cli,
    )


def _cns_for_overrides(args: Namespace | Mapping | None) -> Namespace | None:
    """Locate the inner `args.comicbox` Namespace for CLI overrides, when present."""
    if not isinstance(args, Namespace):
        return None
    candidate = getattr(args, "comicbox", args)
    return candidate if isinstance(candidate, Namespace) else args
