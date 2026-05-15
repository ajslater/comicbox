"""
Environment-variable helpers for online tagging settings.

The resolution chain layers CLI > env > config > keyring; this module owns
the env layer.

Comicbox 4.0 adopts two env-var families for online settings:

1. Per-source credentials (short form) — `COMICBOX_<SOURCE>_<FIELD>`.
   Examples: `COMICBOX_METRON_USERNAME`, `COMICBOX_COMICVINE_API_KEY`.

2. Policy and cache settings (path-aligned) — `COMICBOX_ONLINE_<KEY>`.
   Examples: `COMICBOX_ONLINE_ACCEPT_ONLY`,
   `COMICBOX_ONLINE_CONFIDENCE_THRESHOLD`,
   `COMICBOX_ONLINE_CACHE_DIR`, `COMICBOX_ONLINE_CACHE_TTL`.

Both groups are read explicitly here (rather than via confuse's set_env)
so behavior is predictable across nested template depths.
"""

from collections.abc import Mapping
from typing import Any

from comicbox.online import SOURCE_NAMES

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

# Per-source credential env var names → (source_name, field_name).
_CRED_FIELDS = ("api_key", "username", "password", "url")
# Policy / cache env var names → online_settings field name.
_POLICY_FIELDS: Mapping[str, str] = {
    "ACCEPT_ONLY": "accept_only",
    "SKIP_MULTIPLE": "skip_multiple",
    "IGNORE_EXISTING": "ignore_existing",
    "TAG_ALL_SOURCES": "tag_all_sources",
    "FORCE_SEARCH": "force_search",
    "CONFIDENCE_THRESHOLD": "confidence_threshold",
    "API_BUDGET": "api_budget",
    "CACHE_ENABLED": "cache_enabled",
    "CACHE_DIR": "cache_dir",
    "CACHE_TTL": "cache_ttl",
    "REFRESH_CACHE": "refresh_cache",
    "RETRY_BUDGET": "retry_budget",
}


def parse_bool(value: str) -> bool | None:
    """Parse a boolean env-var value; return None if unrecognised."""
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None


def read_credential_env(env: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """
    Read per-source credentials from `COMICBOX_<SOURCE>_<FIELD>` vars.

    Returns a dict mapping source name → field dict, omitting any source
    or field that has no env var set. Field names match
    ``OnlineSourceCredentials`` attributes.
    """
    result: dict[str, dict[str, str]] = {}
    for source in SOURCE_NAMES:
        for field in _CRED_FIELDS:
            env_name = f"COMICBOX_{source.upper()}_{field.upper()}"
            value = env.get(env_name)
            if value is None:
                continue
            result.setdefault(source, {})[field] = value
    return result


def read_policy_env(env: Mapping[str, str]) -> dict[str, Any]:
    """
    Read online policy / cache settings from `COMICBOX_ONLINE_*` vars.

    Returns a dict keyed by `OnlineSettings` field names; missing env
    vars are omitted. Booleans, floats, and ints are parsed; strings
    are returned as-is. Unparseable booleans/numbers are dropped.
    """
    result: dict[str, Any] = {}
    for env_suffix, field_name in _POLICY_FIELDS.items():
        raw = env.get(f"COMICBOX_ONLINE_{env_suffix}")
        if raw is None:
            continue
        if field_name in {
            "accept_only",
            "skip_multiple",
            "ignore_existing",
            "tag_all_sources",
            "force_search",
            "cache_enabled",
            "refresh_cache",
        }:
            parsed = parse_bool(raw)
            if parsed is not None:
                result[field_name] = parsed
        elif field_name == "confidence_threshold":
            try:
                result[field_name] = float(raw)
            except ValueError:
                continue
        elif field_name == "retry_budget":
            try:
                result[field_name] = int(raw)
            except ValueError:
                continue
        else:
            # cache_dir, cache_ttl — strings; downstream parses cache_ttl.
            result[field_name] = raw
    return result
