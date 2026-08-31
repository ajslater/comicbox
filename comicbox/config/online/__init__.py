"""
Online-tagging configuration.

The online block is about half of the config layer on its own, so it
lives in its own package:

- ``settings`` — the typed dataclass tree, its enums, and the per-source
  ``resolve_*`` helpers. Imports nothing from ``comicbox.formats``.
- ``template`` — the confuse template ``comicbox.config`` mounts at
  ``online``.
- ``build`` — assembly of the dataclasses from the confuse view plus CLI
  overrides.
"""

from comicbox.config.online.build import (
    ALL_SOURCES,
    build_online_settings,
    cns_for_overrides,
    runtime_online_inputs,
)
from comicbox.config.online.settings import (
    DEFAULT_AUTO_THRESHOLD,
    DEFAULT_DISAMBIGUATION_MARGIN,
    DEFAULT_MIN_CONFIDENCE,
    CacheMode,
    Effort,
    MatchMode,
    OnlineAuthSettings,
    OnlineCacheSettings,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceCredentials,
    OnlineSourceLimits,
    OnlineSourceTuning,
    OnlineTuningSettings,
    Prompts,
    resolve_auto_threshold,
    resolve_disambiguation_margin,
    resolve_effort,
    resolve_match,
    resolve_min_confidence,
    resolve_rate_limit,
    resolve_solo_threshold,
)
from comicbox.config.online.template import ONLINE_TEMPLATE

__all__ = (
    "ALL_SOURCES",
    "DEFAULT_AUTO_THRESHOLD",
    "DEFAULT_DISAMBIGUATION_MARGIN",
    "DEFAULT_MIN_CONFIDENCE",
    "ONLINE_TEMPLATE",
    "CacheMode",
    "Effort",
    "MatchMode",
    "OnlineAuthSettings",
    "OnlineCacheSettings",
    "OnlineLookupSettings",
    "OnlineSettings",
    "OnlineSourceCredentials",
    "OnlineSourceLimits",
    "OnlineSourceTuning",
    "OnlineTuningSettings",
    "Prompts",
    "build_online_settings",
    "cns_for_overrides",
    "resolve_auto_threshold",
    "resolve_disambiguation_margin",
    "resolve_effort",
    "resolve_match",
    "resolve_min_confidence",
    "resolve_rate_limit",
    "resolve_solo_threshold",
    "runtime_online_inputs",
)
