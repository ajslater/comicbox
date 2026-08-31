"""
Online (tagging) settings assembly.

Precedence for the online block is CLI > the confuse view, which already
carries env-over-file layering. Only the CLI layer is hand-rolled here
instead of going through confuse because:

- Parse failures must raise typed ``ValueError``s with flag-specific
  messages (``--match: unknown name ...``); confuse templates would
  surface generic validation errors instead.
- The ``--id``/``--series-id`` maps and the per-source auth and tuning
  shapes are keyed by dynamic source names, which confuse's fixed
  ``MappingTemplate``s can't express.
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

from loguru import logger

from comicbox.config.online.settings import (
    DEFAULT_AUTO_THRESHOLD,
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
from comicbox.config.settings import parse_enum
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.formats.base.online.cli_overrides import CliOverrides
from comicbox.formats.base.online.credentials import resolve_credentials
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


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value (order = priority)."""
    for v in values:
        if v is not None:
            return v
    return None


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


# Sentinel for an explicit "all": select every configured source in
# default order, skipping the env/config-file fallback. Distinct from
# None, which means "not specified here — fall through".
ALL_SOURCES: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _RuntimeOnlineInputs:
    """Bag of CLI-derived online inputs for `build_online_settings`."""

    cli_overrides: CliOverrides | None = None
    enabled: bool = False
    sources: tuple[str, ...] | None = None
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
            effort=parse_enum(Effort, "--effort", str(effort_raw))
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
    cli: Callable[[str], Any],
) -> OnlineLookupSettings:
    """Build `OnlineLookupSettings` from CLI > config."""
    match_raw = _coalesce(cli("match"), online_block.lookup.match)
    prompts_raw = _coalesce(cli("prompts"), online_block.lookup.prompts)
    rematch = bool(_coalesce(cli("rematch"), online_block.lookup.rematch))
    # The --all-sources flag asserts "query everything" (first_wins off);
    # absent, the first_wins key comes from the config view.
    all_sources_cli = cli("all_sources")
    first_wins = bool(
        _coalesce(
            None if all_sources_cli is None else not all_sources_cli,
            online_block.lookup.first_wins,
        )
    )
    # Ordered selection: CLI > config view. ALL_SOURCES (or an
    # empty/all-containing list at any layer) collapses to None = every
    # configured source in default order.
    selected = _coalesce(
        runtime.sources,
        _normalize_sources(online_block.lookup.sources, origin="config"),
    )
    if not selected:
        selected = None
    match_mode = (
        parse_enum(MatchMode, "--match", str(match_raw))
        if match_raw
        else MatchMode.AUTO
    )
    prompts_value = (
        parse_enum(Prompts, "--prompts", str(prompts_raw), noun="value")
        if prompts_raw
        else Prompts.ASK
    )

    return OnlineLookupSettings(
        enabled=runtime.enabled,
        sources=selected,
        ids=dict(runtime.ids),
        series_ids=dict(runtime.series_ids),
        match=match_mode,
        prompts=prompts_value,
        rematch=rematch,
        first_wins=first_wins,
    )


def _build_auth_settings(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
) -> OnlineAuthSettings:
    """Build per-source credentials from CLI + config + keyring."""
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
    )
    return OnlineAuthSettings(sources=resolved)


def _build_cache(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    cli: Callable[[str], Any],
) -> OnlineCacheSettings:
    """Build `OnlineCacheSettings` from CLI > config."""
    cache_mode_raw = _coalesce(runtime.cache_mode_cli, online_block.cache.mode)
    cache_mode = (
        cache_mode_raw
        if isinstance(cache_mode_raw, CacheMode)
        else parse_enum(CacheMode, "--cache", str(cache_mode_raw), noun="value")
    )
    cache_dir_raw = _coalesce(cli("cache_dir"), online_block.cache.dir)
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    cache_ttl_raw = _coalesce(cli("cache_ttl"), online_block.cache.ttl)
    return OnlineCacheSettings(
        mode=cache_mode,
        dir=cache_dir,
        ttl=_parse_ttl(cache_ttl_raw),
    )


def _build_tuning(
    online_block: Any,
    cli: Callable[[str], Any],
) -> OnlineTuningSettings:
    """Build `OnlineTuningSettings` from CLI > config."""
    auto_threshold_raw = _coalesce(
        cli("auto_threshold"), online_block.tuning.auto_threshold
    )
    auto_threshold = (
        float(auto_threshold_raw)
        if auto_threshold_raw is not None
        else DEFAULT_AUTO_THRESHOLD
    )
    effort_raw = _coalesce(cli("effort"), online_block.tuning.effort)
    effort_value = (
        parse_enum(Effort, "--effort", str(effort_raw))
        if effort_raw
        else Effort.BALANCED
    )
    retry_budget = int(_coalesce(online_block.tuning.retry_budget, 5))
    per_source = _build_per_source_tuning(online_block)
    return OnlineTuningSettings(
        auto_threshold=auto_threshold,
        effort=effort_value,
        retry_budget=retry_budget,
        per_source=per_source,
    )


def build_online_settings(
    online_block: Any,
    runtime: _RuntimeOnlineInputs,
    *,
    cns: Namespace | None = None,
) -> OnlineSettings:
    """Build the nested `OnlineSettings` from the confuse view + CLI overrides."""

    def _cli(field: str) -> Any:
        return getattr(cns, field, None) if cns is not None else None

    return OnlineSettings(
        lookup=_build_lookup(online_block, runtime, _cli),
        auth=_build_auth_settings(online_block, runtime),
        cache=_build_cache(online_block, runtime, _cli),
        tuning=_build_tuning(online_block, _cli),
    )


def _split_source_names(value: Any) -> tuple[str, ...]:
    """Normalize raw input into an ordered, deduped tuple of lowercase names."""
    if isinstance(value, str):
        value = value.split(",")
    cleaned = (str(v).strip().lower() for v in value)
    return tuple(dict.fromkeys(s for s in cleaned if s))


def _normalize_sources(value: Any, *, origin: str) -> tuple[str, ...] | None:
    """
    Normalize a sources list from CLI/env/config into an ordered tuple.

    Returns None when the value is absent (fall through to the next
    layer), ALL_SOURCES when it's empty or contains the ``all``
    sentinel, and otherwise an order-preserving dedupe of the listed
    names.

    Unknown names raise. Dropping them used to leave an all-unknown
    selection empty, which is the ALL_SOURCES sentinel — so a typo in
    ``--online metrn`` silently widened the run to *every* source
    instead of narrowing it to the one the user asked for. Matches
    ``--id``/``--series-id``, which have always rejected unknown names.
    """
    if value is None:
        return None
    names = _split_source_names(value)
    if not names or "all" in names:
        return ALL_SOURCES
    if unknown := tuple(n for n in names if n not in SOURCE_NAMES):
        reason = (
            f"{origin}: unknown source(s) {', '.join(unknown)}; "
            f"known: {', '.join(SOURCE_NAMES)}"
        )
        raise ValueError(reason)
    return names


def _resolve_runtime_sources(
    online_arg: Any, explicit_id_sources: tuple[str, ...]
) -> tuple[bool, tuple[str, ...] | None]:
    """
    Decide (enabled, selected) from --online-sources + explicit-id presence.

    ``selected`` is ordered (run priority). None = the CLI didn't choose,
    so selection falls through to env/config; ALL_SOURCES = an explicit
    ``--online all``, which overrides the lower layers.
    """
    if online_arg is None:
        if explicit_id_sources:
            return True, explicit_id_sources
        return False, None
    normalized = _normalize_sources(online_arg, origin="--online")
    if not normalized:
        return True, ALL_SOURCES
    return True, tuple(dict.fromkeys((*normalized, *explicit_id_sources)))


def runtime_online_inputs(
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
    explicit_id_sources = tuple(dict.fromkeys((*ids, *series_ids)))
    runtime_enabled, selected = _resolve_runtime_sources(
        getattr(cns, "online_sources", None), explicit_id_sources
    )

    cli_overrides = CliOverrides.from_auth_list(getattr(cns, "auth", None) or ())
    cache_cli = getattr(cns, "cache", None)
    cache_mode_cli = (
        parse_enum(CacheMode, "--cache", str(cache_cli), noun="value")
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


def cns_for_overrides(args: Namespace | Mapping | None) -> Namespace | None:
    """Locate the inner `args.comicbox` Namespace for CLI overrides, when present."""
    if not isinstance(args, Namespace):
        return None
    candidate = getattr(args, "comicbox", args)
    return candidate if isinstance(candidate, Namespace) else args
