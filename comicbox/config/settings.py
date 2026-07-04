"""
Typed runtime config for comicbox.

Built once by ``get_config()`` from the validated confuse AttrDict; every
downstream module takes ``ComicboxSettings`` instead of ``AttrDict``.

The dataclass tree mirrors the YAML config tree and the CLI argument
groups one-for-one:

    comicbox:
      general / read / write / print / convert / compute
      online:
        lookup / auth / cache / tuning

This taxonomy is the source of truth for the config tree. New options
must land under the group that owns their concern.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    from comicbox.formats import MetadataFormats
    from comicbox.formats.sources import MetadataSources
    from comicbox.print import PrintPhases


class MatchMode(str, Enum):
    """
    Match-resolution aggressiveness.

    Strictly increasing aggressiveness: each level auto-writes a
    superset of what the previous one does (ask ⊂ careful ⊂ auto ⊂
    eager). See ``match-resolution-user-doc.md`` for the full
    decision algorithm.

    Inherits from str so dataclass equality, dict keys, and JSON
    serialization all "just work".
    """

    ASK = "ask"
    CAREFUL = "careful"
    AUTO = "auto"
    EAGER = "eager"


class Prompts(str, Enum):
    """Whether comicbox is allowed to prompt the user mid-run."""

    ASK = "ask"
    NEVER = "never"


class Effort(str, Enum):
    """
    API-call effort per comic, for fan-out sources.

    Orthogonal to ``MatchMode`` (which controls how the matcher's
    verdict is applied). ``Effort`` controls how aggressively pre-call
    algorithms trade accuracy for API throughput — it only bites on
    sources that fan out per candidate (ComicVine). Single-call sources
    (Metron since PR #143) have no fan-out to throttle and ignore it.

    - ``MINIMAL``: aggressive pre-filtering; trade accuracy for throughput.
    - ``BALANCED``: today's behavior; the default.
    - ``THOROUGH``: spend API budget freely; max accuracy.
    """

    MINIMAL = "minimal"
    BALANCED = "balanced"
    THOROUGH = "thorough"


class CacheMode(str, Enum):
    """Cache tri-state: on / off / refresh."""

    ON = "on"
    OFF = "off"
    REFRESH = "refresh"


# Built-in defaults for per-source tuning knobs. Internal — not surfaced
# in user-facing CLI/docs but available as per-source YAML overrides.
DEFAULT_MIN_CONFIDENCE = 0.50
DEFAULT_DISAMBIGUATION_MARGIN = 0.10
# Solo-viable auto-write floor. When the matcher returns exactly one
# candidate clearing ``min_confidence``, ``AUTO``/``EAGER`` modes
# auto-write only if it also clears this floor. Default equals the
# global confidence threshold (0.95), so solo cases need the same bar
# as multi-candidate unambiguous wins.
DEFAULT_SOLO_THRESHOLD = 0.85


@dataclass(frozen=True, slots=True)
class GeneralSettings:
    """Cross-cutting options that don't fit a verb-specific group."""

    config: str | Path | None = None
    recurse: bool = False
    dry_run: bool = False
    loglevel: str | int = "INFO"
    dest_path: str | Path = "."
    delete_keys: frozenset[str] = field(default_factory=frozenset)
    delete_orig: bool = False
    metadata: Mapping | None = None
    metadata_cli: tuple[str, ...] | None = None
    metadata_format: str | None = None
    jobs: int = 1
    tagger: str | None = None
    theme: str | None = "gruvbox-dark"


@dataclass(frozen=True, slots=True)
class ReadSettings:
    """Which metadata sources to load and in what merge order."""

    formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    except_formats: frozenset[str] | None = None  # YAML key: "except"
    # Merge precedence (None = ``MetadataSources`` enum order). Expert
    # knob; YAML-only.
    merge_order: "tuple[MetadataSources, ...] | None" = None


class WriteMode(str, Enum):
    """
    How a write merges its patch against the comic's existing metadata.

    - ``additive``: deep-merge via mergedeep ADDITIVE. Dicts recurse;
      lists / tuples / sets at conflicting paths *concatenate*; scalars
      and other leaves *replace*. Default.
    - ``update``: ``dict.update()`` at ROOT_TAG. Replaces top-level keys
      wholesale; siblings of a replaced key are dropped.
    - ``replace``: deep-merge via mergedeep REPLACE. Dicts recurse;
      everything else (scalars, lists, tuples, sets) *replaces*. Codex's
      "rename publisher from `Foo Comics` to `Foo`" use case wants this
      when paired with list-typed fields whose patch is meant to be the
      new complete value rather than an append. For dict-of-dict
      structures (most of comicbox's schema) ``additive`` and ``replace``
      are indistinguishable.
    """

    ADDITIVE = "additive"
    UPDATE = "update"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class WriteSettings:
    """Which metadata formats to write back, and how."""

    formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    # Default merge behavior on write. The legacy ``replace`` bool is
    # kept as a deprecated alias: ``replace=True`` maps to
    # ``mode=WriteMode.UPDATE`` (its historical meaning — UpdateMerger).
    mode: WriteMode = WriteMode.ADDITIVE
    replace: bool = False  # DEPRECATED: alias for ``mode=update``.
    stamp: bool = False
    stamp_notes: bool = True
    delete_all_tags: bool = False


@dataclass(frozen=True, slots=True)
class PrintSettings:
    """Phases to print and whether to validate."""

    phases: "frozenset[PrintPhases]" = field(default_factory=frozenset)
    validate: bool = False


@dataclass(frozen=True, slots=True)
class ConvertSettings:
    """Archive conversion actions: cbz, rename, page/cover extraction, import/export."""

    cbz: bool | None = None
    rename: bool | None = None
    extract_pages_from: int | None = None
    extract_pages_to: int | None = None
    extract_covers: bool | None = None
    import_paths: tuple[Path, ...] = ()
    export_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    pdf_pages: str = ""


@dataclass(frozen=True, slots=True)
class ComputeSettings:
    """Derived-metadata switches. YAML-only — set-once preferences."""

    pages: bool = False
    page_count: bool = True


@dataclass(frozen=True, slots=True)
class OnlineLookupSettings:
    """What to look up and how aggressively to act on results."""

    # Runtime-only (CLI-derived; never lives in the config file).
    enabled: bool = False
    ids: Mapping[str, int] = field(default_factory=dict)
    series_ids: Mapping[str, int] = field(default_factory=dict)

    # Ordered source selection AND run priority: the first listed source
    # runs first, and with ``first_wins`` its match ends the lookup.
    # None = every configured source in SOURCE_NAMES order. Durable via
    # the ``online.lookup.sources`` config-file key; CLI --online and
    # COMICBOX_ONLINE_SOURCES override it.
    sources: tuple[str, ...] | None = None

    # Behavior toggles.
    match: MatchMode = MatchMode.AUTO
    prompts: Prompts = Prompts.ASK
    rematch: bool = False
    # Stop after the first source that contributes data (the cheap,
    # default mode). False = query every selected source and merge
    # (CLI: --all-sources).
    first_wins: bool = True


@dataclass(frozen=True, slots=True)
class OnlineSourceCredentials:
    """
    Resolved credentials for one online source.

    Field membership is per-source: Metron uses ``user``/``password``/``url``;
    ComicVine uses ``key``/``url``. The source's ``is_configured()``
    decides which fields are required.
    """

    user: str | None = None
    password: str | None = None
    key: str | None = None
    url: str | None = None

    @override
    def __repr__(self) -> str:
        """Redact secret-bearing fields so this object is log-safe."""
        return (
            "OnlineSourceCredentials("
            f"user={self.user!r}, "
            f"password={'***' if self.password else None}, "
            f"key={'***' if self.key else None}, "
            f"url={self.url!r})"
        )


@dataclass(frozen=True, slots=True)
class OnlineAuthSettings:
    """Per-source credentials, indexed by source name."""

    sources: Mapping[str, OnlineSourceCredentials] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OnlineCacheSettings:
    """Where the online response cache lives and how long entries survive."""

    mode: CacheMode = CacheMode.ON
    dir: Path | None = None
    ttl: timedelta = field(default_factory=lambda: timedelta(days=7))


@dataclass(frozen=True, slots=True)
class OnlineSourceLimits:
    """
    Per-source rate-limit overrides.

    All fields default to None, in which case comicbox lets the upstream
    library (mokkari / simyan) apply its own documented rate limits.
    Set any field to override that source's bucket — useful when the
    user has a higher API tier or wants to be more conservative.

    Documented defaults live in
    ``comicbox.formats.base.online.rate_limits`` for citation / audit.
    """

    # Used by Metron (mokkari).
    per_minute: int | None = None
    per_day: int | None = None
    # Used by ComicVine (simyan).
    per_second: int | None = None
    per_hour: int | None = None


@dataclass(frozen=True, slots=True)
class OnlineSourceTuning:
    """
    Per-source overrides for tuning knobs.

    Any field left at None falls back to the global default in
    ``OnlineTuningSettings``. Advanced fields
    (``min_confidence``, ``disambiguation_margin``, ``solo_threshold``)
    are undocumented in user-facing reference but live here so power
    users can adjust them per source via YAML.
    """

    auto_threshold: float | None = None
    effort: Effort | None = None
    min_confidence: float | None = None
    disambiguation_margin: float | None = None
    solo_threshold: float | None = None
    rate_limit: OnlineSourceLimits = field(default_factory=OnlineSourceLimits)


@dataclass(frozen=True, slots=True)
class OnlineTuningSettings:
    """Global tuning defaults plus per-source overrides."""

    # Global defaults.
    auto_threshold: float = 0.85
    effort: Effort = Effort.BALANCED
    retry_budget: int = 5

    # Per-source overrides (keyed by source name).
    per_source: Mapping[str, OnlineSourceTuning] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OnlineSettings:
    """Online metadata-tagging settings, split into four concern groups."""

    lookup: OnlineLookupSettings = field(default_factory=OnlineLookupSettings)
    auth: OnlineAuthSettings = field(default_factory=OnlineAuthSettings)
    cache: OnlineCacheSettings = field(default_factory=OnlineCacheSettings)
    tuning: OnlineTuningSettings = field(default_factory=OnlineTuningSettings)


def _tuning_for(settings: OnlineSettings, source_name: str) -> OnlineSourceTuning:
    return settings.tuning.per_source.get(source_name) or OnlineSourceTuning()


def resolve_match(settings: OnlineSettings, source_name: str) -> MatchMode:
    """Per-source match mode falls back to the global default."""
    # No per-source override on this knob (carried in the global
    # ``lookup.match``); helper exists for symmetry and future expansion.
    del source_name  # unused — kept for signature consistency
    return settings.lookup.match


def resolve_auto_threshold(settings: OnlineSettings, source_name: str) -> float:
    """Per-source auto_threshold override > global default."""
    override = _tuning_for(settings, source_name).auto_threshold
    return override if override is not None else settings.tuning.auto_threshold


def resolve_effort(settings: OnlineSettings, source_name: str) -> Effort:
    """Per-source effort override > global default."""
    override = _tuning_for(settings, source_name).effort
    return override if override is not None else settings.tuning.effort


def resolve_min_confidence(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    override = _tuning_for(settings, source_name).min_confidence
    return override if override is not None else DEFAULT_MIN_CONFIDENCE


def resolve_disambiguation_margin(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    override = _tuning_for(settings, source_name).disambiguation_margin
    return override if override is not None else DEFAULT_DISAMBIGUATION_MARGIN


def resolve_solo_threshold(settings: OnlineSettings, source_name: str) -> float:
    """Per-source override > built-in default. Not user-exposed today."""
    override = _tuning_for(settings, source_name).solo_threshold
    return override if override is not None else DEFAULT_SOLO_THRESHOLD


def resolve_rate_limit(
    settings: OnlineSettings, source_name: str
) -> OnlineSourceLimits:
    """Per-source rate-limit override; empty default = use upstream library default."""
    return _tuning_for(settings, source_name).rate_limit


def resolve_credentials(
    settings: OnlineSettings, source_name: str
) -> OnlineSourceCredentials:
    """Per-source credentials; returns an empty record if no entry."""
    return settings.auth.sources.get(source_name) or OnlineSourceCredentials()


@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    """Typed runtime config for comicbox, organized by verb taxonomy."""

    general: GeneralSettings
    read: ReadSettings
    write: WriteSettings
    print: PrintSettings
    convert: ConvertSettings
    compute: ComputeSettings
    online: OnlineSettings

    # CLI positional args.
    paths: tuple[str | Path | None, ...] = ()

    # Computed (derived in compute_config(); kept flat for ergonomics —
    # they're read by many call sites and the flat names are clearer).
    all_write_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    read_filename_formats: "frozenset[MetadataFormats]" = field(
        default_factory=frozenset
    )
    read_file_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    read_metadata_lower_filenames: frozenset[str] = field(default_factory=frozenset)
    is_read_comments: bool = False
    is_skip_computed_from_tags: bool = False
