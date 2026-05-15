"""
Typed runtime config for comicbox.

Built once by ``get_config()`` from the validated confuse AttrDict; every
downstream module takes ``ComicboxSettings`` instead of ``AttrDict``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comicbox.formats import MetadataFormats
    from comicbox.print import PrintPhases
    from comicbox.sources import MetadataSources


class Policy(str, Enum):
    """
    Match-resolution policy.

    Strictly increasing aggressiveness: each level auto-writes a
    superset of what the previous one does (always-prompt ⊂ strict ⊂
    normal ⊂ eager). See `match-resolution-user-doc.md` for the full
    decision algorithm.

    Inherits from str so dataclass equality, dict keys, and JSON
    serialization all "just work" without StrEnum (ty's stdlib stubs
    don't recognize StrEnum yet).
    """

    ALWAYS_PROMPT = "always-prompt"
    STRICT = "strict"
    NORMAL = "normal"
    EAGER = "eager"


class APIBudget(str, Enum):
    """
    API-call budget per comic.

    Orthogonal to `Policy` (which controls how the matcher's verdict is
    applied). `APIBudget` controls how aggressively pre-call algorithms
    trade accuracy for API throughput. See `06-api-budget-spec.md` for
    the full design.

    - `EXHAUSTIVE`: spend API budget freely; max accuracy.
    - `BALANCED`: today's behavior; the default.
    - `FAST`: aggressive pre-filtering; trade accuracy for throughput.

    Inherits from str for the same reasons as `Policy` (dataclass
    equality, dict keys, JSON without StrEnum).
    """

    EXHAUSTIVE = "exhaustive"
    BALANCED = "balanced"
    FAST = "fast"


@dataclass(frozen=True, slots=True)
class OnlineSourceCredentials:
    """
    Resolved credentials for one online source.

    A source is "configured" iff its required fields resolve to non-null.
    Each source decides which fields are required.
    """

    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class OnlineSourceLimits:
    """
    Per-source rate-limit overrides.

    All fields default to None, in which case comicbox lets the upstream
    library (mokkari / simyan) apply its own documented rate limits. Set
    any field to override that source's bucket — useful when the user has
    a higher API tier or wants to be more conservative.

    Documented defaults (as of 2026-05) live in
    `comicbox.online.rate_limits` for citation / audit.
    """

    # Used by Metron (mokkari).
    per_minute: int | None = None
    per_day: int | None = None
    # Used by ComicVine (simyan).
    per_second: int | None = None
    per_hour: int | None = None


# Calibration defaults — internal, not exposed as user-facing knobs.
DEFAULT_MIN_CONFIDENCE = 0.50
DEFAULT_DISAMBIGUATION_MARGIN = 0.10
# Solo-viable auto-write floor (Phase E). When the matcher returns exactly
# one candidate clearing `min_confidence`, `NORMAL`/`EAGER` policies have
# historically auto-written it regardless of how close to the confidence
# threshold it scored. That carve-out powers the worst silent-failure
# pattern observed at scale: a single weak candidate (e.g. score=0.88)
# wins by default when CV's search didn't return the actual right answer.
#
# Setting the floor equal to the default confidence threshold (0.95)
# means: even solo candidates need to clear the same bar as multi-candidate
# unambig cases to auto-write. Below the floor, solo cases route to
# PROMPT — the user picks. Per-source override available for callers who
# want the old permissive behavior (set to 0.50 = min_confidence).
DEFAULT_SOLO_CONFIDENCE_THRESHOLD = 0.95


@dataclass(frozen=True, slots=True)
class OnlineSettings:
    """Online metadata-tagging settings."""

    # Runtime-only (CLI-derived; never lives in the config file)
    enabled: bool = False
    selected_sources: frozenset[str] | None = None
    # First-wins vs tag-with-every-source. Default False means: stop after
    # the first online source that contributes data (or has a stored id
    # from a prior tag). Sources passed via --id / --series-id always run
    # regardless. Order is the priority of `_DEFAULT_SOURCE_FACTORIES`
    # in `box/online_lookup.py` (metron first, then comicvine).
    tag_all_sources: bool = False
    # When True, force a full search even if the comic already has a
    # stored identifier for the source. Use to override stale or wrong
    # ids without manually passing --id. Does not override an explicit
    # --id flag (which is the strongest user signal).
    force_search: bool = False
    explicit_ids: Mapping[str, int] = field(default_factory=dict)
    # Optional `--series-id <db>:<id>`: skips the per-source series-discovery
    # step and constrains issue lookup to the named series id directly.
    explicit_series_ids: Mapping[str, int] = field(default_factory=dict)

    # Match-resolution policy (the new scheme; see match-resolution-user-doc.md).
    policy: Policy = Policy.NORMAL
    unattended: bool = False
    # API-call budget per comic (see 06-api-budget-spec.md). Controls
    # pre-call algorithms (series-name pre-filter strictness, per-source
    # search breadth caps) that trade accuracy for API throughput. Default
    # `BALANCED` is today's behavior — Phase A ships the levers dormant
    # until Phase B calibration picks the real thresholds.
    api_budget: APIBudget = APIBudget.BALANCED
    # Per-source overrides for `policy`, `confidence_threshold`, and
    # `api_budget`. Resolution: per-source > global > built-in default.
    # Empty dict means "use global".
    policy_per_source: Mapping[str, Policy] = field(default_factory=dict)
    confidence_threshold_per_source: Mapping[str, float] = field(default_factory=dict)
    api_budget_per_source: Mapping[str, APIBudget] = field(default_factory=dict)
    # Internal-only per-source overrides (no CLI today; ready for when
    # calibration data justifies surfacing them).
    min_confidence_per_source: Mapping[str, float] = field(default_factory=dict)
    disambiguation_margin_per_source: Mapping[str, float] = field(default_factory=dict)
    # Floor below which a `solo_viable` candidate (single viable hit) is
    # NOT auto-written under NORMAL/EAGER — falls through to PROMPT
    # instead. Default `DEFAULT_SOLO_CONFIDENCE_THRESHOLD` (0.95) matches
    # the global confidence threshold; setting per-source to 0.50 restores
    # the pre-Phase-E permissive behavior (any solo candidate above
    # min_confidence auto-writes).
    solo_confidence_threshold_per_source: Mapping[str, float] = field(
        default_factory=dict
    )

    # Persistent (config file + env var; CLI flag may override)
    # Auto-write threshold. Calibrated against the spring-2026 fixture set:
    # 0.85 produced ~7% wrong auto-writes in the 0.85-0.95 band (mostly
    # wrong-volume picks for series with reboots like Watchmen 1986 vs
    # Absolute Watchmen 2005). 0.95 converts those into prompts while
    # preserving the high-volume of confident matches.
    confidence_threshold: float = 0.95
    # Legacy flags (deprecated; matcher no longer reads these directly post-M-policy).
    # Kept for translation-layer compatibility — the CLI parser maps them to
    # the new `policy` / `unattended` fields with deprecation warnings.
    skip_multiple: bool = False
    accept_only: bool = False
    ignore_existing: bool = False

    cache_enabled: bool = True
    cache_dir: Path | None = None
    cache_ttl: timedelta = field(default_factory=lambda: timedelta(days=7))
    refresh_cache: bool = False

    retry_budget: int = 5

    # Per-source credentials and config (keyed by source name).
    sources: Mapping[str, OnlineSourceCredentials] = field(default_factory=dict)
    # Per-source rate-limit overrides (keyed by source name). Empty dict
    # for any source means "use upstream library default."
    source_limits: Mapping[str, OnlineSourceLimits] = field(default_factory=dict)


def resolve_policy(settings: OnlineSettings, source_name: str) -> Policy:
    """Per-source override > global default."""
    return settings.policy_per_source.get(source_name, settings.policy)


def resolve_confidence_threshold(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > global default."""
    return settings.confidence_threshold_per_source.get(
        source_name, settings.confidence_threshold
    )


def resolve_min_confidence(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    return settings.min_confidence_per_source.get(source_name, DEFAULT_MIN_CONFIDENCE)


def resolve_disambiguation_margin(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    return settings.disambiguation_margin_per_source.get(
        source_name, DEFAULT_DISAMBIGUATION_MARGIN
    )


def resolve_solo_confidence_threshold(
    settings: OnlineSettings, source_name: str
) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    return settings.solo_confidence_threshold_per_source.get(
        source_name, DEFAULT_SOLO_CONFIDENCE_THRESHOLD
    )


def resolve_api_budget(settings: OnlineSettings, source_name: str) -> APIBudget:
    """Per-source override > global default."""
    return settings.api_budget_per_source.get(source_name, settings.api_budget)


@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    """Typed runtime config for comicbox."""

    # Options
    compute_pages: bool
    compute_page_count: bool
    config: str | Path | None
    delete_all_tags: bool
    delete_keys: frozenset[str]
    delete_orig: bool
    dest_path: str | Path
    dry_run: bool
    loglevel: str | int
    metadata: Mapping | None
    metadata_format: str | None
    metadata_cli: tuple[str, ...] | None
    pdf_page_format: str
    read: "frozenset[MetadataFormats]"
    read_ignore: frozenset[str] | None
    recurse: bool
    replace_metadata: bool
    stamp: bool
    stamp_notes: bool
    tagger: str
    theme: str | None
    # Actions
    cbz: bool | None
    covers: bool | None
    export: "frozenset[MetadataFormats]"
    import_paths: tuple[Path, ...]
    index_from: int | None
    index_to: int | None
    print: "frozenset[PrintPhases]"
    rename: bool | None
    validate: bool | None
    write: "frozenset[MetadataFormats]"
    # Targets
    paths: tuple[str | Path | None, ...]
    # Computed (derived in compute_config(); nested under "computed" in the
    # confuse template as an implementation convenience, but flat here).
    all_write_formats: "frozenset[MetadataFormats]"
    read_filename_formats: "frozenset[MetadataFormats]"
    read_file_formats: "frozenset[MetadataFormats]"
    read_metadata_lower_filenames: frozenset[str]
    is_read_comments: bool
    is_skip_computed_from_tags: bool
    # Merge ordering (None = use MetadataSources enum order).
    merge_order: "tuple[MetadataSources, ...] | None"
    # Parallel workers across files (1 = serial, no thread pool).
    jobs: int
    # Online metadata-tagging settings (always present).
    online: OnlineSettings
