"""Confuse config for comicbox."""

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
    APIBudget,
    ComicboxSettings,
    OnlineSettings,
    OnlineSourceLimits,
    Policy,
)
from comicbox.identifiers import PARSE_COMICVINE_RE
from comicbox.online import SOURCE_NAMES
from comicbox.online.cli_overrides import CliOverrides
from comicbox.online.credentials import resolve_credentials
from comicbox.online.env import read_policy_env
from comicbox.sources import MetadataSources
from comicbox.version import PACKAGE_NAME

# ComicVine resource-type prefix for issues. CV ids are sometimes shown
# with a 4-digit type prefix; for our purposes we only accept issue ids.
_CV_ISSUE_RESOURCE_TYPE = 4000

# Any non-Mapping container type — set/frozenset/tuple/list all pass.
# `_build_settings` normalizes the validated value into the right immutable
# type for the dataclass (frozenset for set-like fields, tuple for sequences),
# so the template intentionally doesn't pin element types here.
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

_ONLINE_SOURCE_TEMPLATE = MappingTemplate(
    {
        "api_key": Optional(str),
        "username": Optional(str),
        "password": Optional(str),
        "url": Optional(str),
        # Optional per-source rate-limit overrides. None / unset = use the
        # upstream library's documented default (see comicbox.online.rate_limits).
        "rate_limit": Optional(_RATE_LIMIT_TEMPLATE),
    }
)

_ONLINE_TEMPLATE = MappingTemplate(
    {
        "policy": Optional(str),
        "unattended": bool,
        "confidence_threshold": Number(),
        # Legacy flags — still accepted for backward compat; the CLI
        # parser translates them to `policy` / `unattended` with a
        # deprecation warning.
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
                # Parallel workers across files (1 = serial).
                "jobs": Integer(),
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
    explicit_series_ids: Mapping[str, int] = field(default_factory=dict)
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

    # `--confidence-threshold` is action=append (list of strings) on the
    # CLI; programmatic callers may still pass a single float for backward
    # compat. Same for `--policy` (list[str]) vs a single string.
    threshold_cli_raw = _cli("confidence_threshold")
    if threshold_cli_raw is not None and not isinstance(threshold_cli_raw, list):
        threshold_cli_raw = [str(threshold_cli_raw)]
    policy_cli_raw = _cli("policy")
    if policy_cli_raw is not None and not isinstance(policy_cli_raw, list):
        policy_cli_raw = [str(policy_cli_raw)]
    api_budget_cli_raw = _cli("api_budget")
    if api_budget_cli_raw is not None and not isinstance(api_budget_cli_raw, list):
        api_budget_cli_raw = [str(api_budget_cli_raw)]
    resolved_policy = _resolve_match_policy(
        policy_cli=policy_cli_raw,
        unattended_cli=_cli("unattended"),
        threshold_cli=threshold_cli_raw,
        accept_only_cli=_cli("accept_only"),
        skip_multiple_cli=_cli("skip_multiple"),
        online_block=online,
        policy_env=policy_env,
    )
    api_budget_global, api_budget_per_source = _resolve_api_budget(
        api_budget_cli=api_budget_cli_raw,
        online_block=online,
        policy_env=policy_env,
    )
    ignore_existing = bool(
        _coalesce(
            _cli("ignore_existing"),
            policy_env.get("ignore_existing"),
            online.ignore_existing,
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

    source_limits = _resolve_source_limits(online)

    return OnlineSettings(
        enabled=runtime.enabled,
        selected_sources=runtime.selected_sources,
        explicit_ids=dict(runtime.explicit_ids),
        explicit_series_ids=dict(runtime.explicit_series_ids),
        policy=resolved_policy.policy,
        unattended=resolved_policy.unattended,
        api_budget=api_budget_global,
        api_budget_per_source=api_budget_per_source,
        policy_per_source=resolved_policy.policy_per_source,
        confidence_threshold=resolved_policy.confidence_threshold,
        confidence_threshold_per_source=resolved_policy.confidence_threshold_per_source,
        ignore_existing=ignore_existing,
        cache_enabled=cache_enabled,
        cache_dir=cache_dir,
        cache_ttl=_parse_ttl(cache_ttl_raw),
        refresh_cache=refresh_cache,
        retry_budget=retry_budget,
        sources=sources_creds,
        source_limits=source_limits,
    )


_CV_VOLUME_RESOURCE_TYPE = 4050


def _parse_explicit_id(source: str, raw: str) -> int:
    """
    Normalize the raw `--id` value for a source into a numeric issue id.

    ComicVine ids are sometimes shown with a 4-digit resource-type prefix
    (e.g. `4000-12345` where `4000` = issue). This accepts both
    `--id comicvine:12345` and `--id comicvine:4000-12345`. Other resource
    types (e.g. 4050 volume) are rejected since the ID flag is for tagging
    a comic by issue id.

    All other sources expect a bare integer.
    """
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


def _parse_db_id_list(
    raw_list: Iterable[str] | None,
    flag_name: str,
    parse_value: Callable[[str, str], int],
) -> dict[str, int]:
    """
    Parse a list of `DB:ID` strings (from `--id` or `--series-id`).

    `parse_value(source, value)` converts each value to an int (with
    source-specific normalization, e.g. CV's `4000-NNN` form).
    """
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
class _ResolvedMatchPolicy:
    """Output of resolving CLI / env / config / legacy flags into the new policy fields."""

    policy: Policy
    unattended: bool
    policy_per_source: dict[str, Policy]
    confidence_threshold: float
    confidence_threshold_per_source: dict[str, float]


def _resolve_source_limits(online: Any) -> dict[str, OnlineSourceLimits]:
    """
    Read per-source `rate_limit` blocks into `OnlineSourceLimits` objects.

    Config-file / env only — there's no CLI flag because this is a
    "I have a higher API tier" knob, not a per-run one. Sources with no
    overrides set are omitted from the returned dict (which means the
    source code falls through to the upstream library's default).
    """
    out: dict[str, OnlineSourceLimits] = {}
    for source in SOURCE_NAMES:
        block: Any = getattr(online, source, None)
        rl: Any = getattr(block, "rate_limit", None) if block is not None else None
        if rl is None:
            continue
        limits = OnlineSourceLimits(
            per_minute=getattr(rl, "per_minute", None),
            per_day=getattr(rl, "per_day", None),
            per_second=getattr(rl, "per_second", None),
            per_hour=getattr(rl, "per_hour", None),
        )
        # Skip the entry if every field is None — equivalent to upstream default.
        if any(
            v is not None
            for v in (
                limits.per_minute,
                limits.per_day,
                limits.per_second,
                limits.per_hour,
            )
        ):
            out[source] = limits
    return out


def _resolve_match_policy(
    *,
    policy_cli: list[str] | None,
    unattended_cli: bool | None,
    threshold_cli: list[str] | None,
    accept_only_cli: bool | None,
    skip_multiple_cli: bool | None,
    online_block: Any,
    policy_env: Mapping[str, Any],
) -> _ResolvedMatchPolicy:
    """
    Resolve match-resolution policy from CLI / env / config / legacy flags.

    New flags (`--policy`, `--unattended`, per-source
    `--confidence-threshold`) take precedence. Legacy flags
    (`--accept-only`, `--skip-multiple`) translate into the new fields
    with deprecation warnings when the new flags weren't supplied.
    """
    policy_global, policy_per_source = _parse_global_or_per_source_list(
        policy_cli, "--policy", _parse_policy_value
    )
    threshold_global, threshold_per_source = _parse_global_or_per_source_list(
        threshold_cli, "--confidence-threshold", _parse_confidence_threshold_value
    )

    unattended = bool(_coalesce(unattended_cli, policy_env.get("unattended")) or False)

    # Translate legacy --accept-only and --skip-multiple when the new
    # flags are absent. Process skip_multiple first (sets STRICT), then
    # accept_only (overrides to NORMAL) so the both-flags-set case maps
    # to "unattended + auto-write solo viable" — matching old behavior.
    legacy_skip = bool(
        skip_multiple_cli
        or _coalesce(policy_env.get("skip_multiple"), online_block.skip_multiple)
    )
    legacy_accept = bool(
        accept_only_cli
        or _coalesce(policy_env.get("accept_only"), online_block.accept_only)
    )
    if legacy_skip:
        logger.warning(
            "--skip-multiple is deprecated; use --unattended --policy strict"
        )
        if unattended_cli is None:
            unattended = True
        if policy_global is None:
            policy_global = Policy.STRICT
    if legacy_accept:
        logger.warning(
            "--accept-only is deprecated; the new default --policy normal "
            "covers its behavior"
        )
        # accept_only's solo-viable rule supersedes skip_multiple's strict;
        # only override if the user didn't pass --policy explicitly.
        if policy_cli is None:
            policy_global = Policy.NORMAL

    if policy_global is None:
        policy_global = Policy.NORMAL  # default

    if policy_global is Policy.ALWAYS_PROMPT and unattended:
        reason = (
            "--policy always-prompt with --unattended is invalid: every "
            "comic would skip and no work would be done. Drop one."
        )
        raise ValueError(reason)

    threshold_value = float(
        _coalesce(
            threshold_global,
            policy_env.get("confidence_threshold"),
            online_block.confidence_threshold,
        )
    )

    return _ResolvedMatchPolicy(
        policy=policy_global,
        unattended=unattended,
        policy_per_source=policy_per_source,
        confidence_threshold=threshold_value,
        confidence_threshold_per_source=threshold_per_source,
    )


def _parse_global_or_per_source_list(
    raw_list: Iterable[str] | None,
    flag_name: str,
    parse_value: Callable[[str], Any],
) -> tuple[Any | None, dict[str, Any]]:
    """
    Parse a `--policy` / `--confidence-threshold` style flag.

    Each occurrence is either a bare value (sets the global default)
    or `<source>:<value>` (per-source override). Returns
    `(global_value_or_None, per_source_dict)`. Last-wins for duplicates.

    Validates source names against `SOURCE_NAMES` and lets `parse_value`
    raise on bad values.
    """
    if not raw_list:
        return None, {}
    global_value: Any | None = None
    per_source: dict[str, Any] = {}
    for raw in raw_list:
        if ":" in raw:
            src, _, value = raw.partition(":")
            src = src.strip().lower()
            if src not in SOURCE_NAMES:
                reason = (
                    f"{flag_name}: unknown source {src!r}; "
                    f"known: {', '.join(SOURCE_NAMES)}"
                )
                raise ValueError(reason)
            per_source[src] = parse_value(value.strip())
        else:
            global_value = parse_value(raw.strip())
    return global_value, per_source


def _parse_policy_value(raw: str) -> Policy:
    try:
        return Policy(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(p.value for p in Policy)
        reason = f"--policy: unknown name {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _parse_confidence_threshold_value(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        reason = f"--confidence-threshold: non-numeric value {raw!r}"
        raise ValueError(reason) from exc
    if not 0.0 <= value <= 1.0:
        reason = f"--confidence-threshold must be in [0, 1], got {value}"
        raise ValueError(reason)
    return value


def _parse_api_budget_value(raw: str) -> APIBudget:
    try:
        return APIBudget(raw.strip().lower())
    except ValueError as exc:
        valid = ", ".join(b.value for b in APIBudget)
        reason = f"--api-budget: unknown name {raw!r}; valid: {valid}"
        raise ValueError(reason) from exc


def _resolve_api_budget(
    *,
    api_budget_cli: list[str] | None,
    online_block: Any,
    policy_env: Mapping[str, Any],
) -> tuple[APIBudget, dict[str, APIBudget]]:
    """
    Resolve `--api-budget` CLI values plus env / config defaults.

    Returns the global budget and the per-source override map. Resolution
    order matches the existing `--policy` pattern: CLI > env > config
    file > built-in default (`BALANCED`).
    """
    global_value, per_source = _parse_global_or_per_source_list(
        api_budget_cli, "--api-budget", _parse_api_budget_value
    )
    if global_value is None:
        # Env or config-file default if user didn't set CLI.
        env_value = policy_env.get("api_budget")
        if env_value is not None:
            global_value = _parse_api_budget_value(str(env_value))
        else:
            config_value = getattr(online_block, "api_budget", None)
            if config_value is not None:
                global_value = _parse_api_budget_value(str(config_value))
            else:
                global_value = APIBudget.BALANCED
    return global_value, per_source


def _parse_explicit_series_id(source: str, raw: str) -> int:
    """
    Normalize the raw `--series-id` value into a numeric series/volume id.

    For ComicVine, accepts both `comicvine:NNN` and `comicvine:4050-NNN`
    (volume resource type). Other resource types are rejected. All other
    sources expect a bare integer (Metron series id, etc.).
    """
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

    explicit_ids = _parse_db_id_list(
        getattr(cns, "explicit_ids", None), "--id", _parse_explicit_id
    )
    explicit_series_ids = _parse_db_id_list(
        getattr(cns, "explicit_series_ids", None),
        "--series-id",
        _parse_explicit_series_id,
    )

    explicit_id_sources = frozenset(explicit_ids.keys()) | frozenset(
        explicit_series_ids.keys()
    )

    selected: frozenset[str] | None
    if online_arg is None:
        # `--id <source>:<id>` implicitly activates online for that source,
        # even without `--online`.
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
        # `all` (or an empty list) is the "every configured source" sentinel.
        if not normalized or "all" in normalized:
            selected = None
        else:
            # Always include explicit-id sources so a user `--id`
            # never gets silently filtered out by the `--online <list>` filter.
            selected = normalized | explicit_id_sources

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
        explicit_series_ids=explicit_series_ids,
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
        # Parallel workers (clamped to >= 1).
        jobs=max(1, int(inner.jobs)),
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
