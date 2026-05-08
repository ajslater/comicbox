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


# Calibration defaults — internal, not exposed as user-facing knobs.
DEFAULT_MIN_CONFIDENCE = 0.50
DEFAULT_DISAMBIGUATION_MARGIN = 0.10


@dataclass(frozen=True, slots=True)
class OnlineSettings:
    """Online metadata-tagging settings."""

    # Runtime-only (CLI-derived; never lives in the config file)
    enabled: bool = False
    selected_sources: frozenset[str] | None = None
    explicit_ids: Mapping[str, int] = field(default_factory=dict)
    # Optional `--series-id <db>:<id>`: skips the per-source series-discovery
    # step and constrains issue lookup to the named series id directly.
    explicit_series_ids: Mapping[str, int] = field(default_factory=dict)

    # Match-resolution policy (the new scheme; see match-resolution-user-doc.md).
    policy: Policy = Policy.NORMAL
    unattended: bool = False
    # Per-source overrides for `policy` and `confidence_threshold`. Resolution:
    # per-source > global > built-in default. Empty dict means "use global".
    policy_per_source: Mapping[str, Policy] = field(default_factory=dict)
    confidence_threshold_per_source: Mapping[str, float] = field(default_factory=dict)
    # Internal-only per-source overrides (no CLI today; ready for when
    # calibration data justifies surfacing them).
    min_confidence_per_source: Mapping[str, float] = field(default_factory=dict)
    disambiguation_margin_per_source: Mapping[str, float] = field(default_factory=dict)

    # Persistent (config file + env var; CLI flag may override)
    confidence_threshold: float = 0.85
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
