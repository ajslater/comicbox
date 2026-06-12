"""
Environment-variable helpers for online tagging settings.

The resolution chain layers CLI > env > config > keyring; this module owns
the env layer.

Two env-var families:

1. Per-source credentials — ``COMICBOX_<SOURCE>_<FIELD>``:
   - Metron: ``COMICBOX_METRON_USER``, ``COMICBOX_METRON_PASS``,
     ``COMICBOX_METRON_URL``
   - ComicVine: ``COMICBOX_COMICVINE_KEY``, ``COMICBOX_COMICVINE_URL``

2. Online lookup / cache / tuning settings — ``COMICBOX_ONLINE_<KEY>``:
   ``COMICBOX_ONLINE_MATCH``, ``COMICBOX_ONLINE_PROMPTS``,
   ``COMICBOX_ONLINE_REMATCH``, ``COMICBOX_ONLINE_ALL_SOURCES``,
   ``COMICBOX_ONLINE_AUTO_THRESHOLD``, ``COMICBOX_ONLINE_EFFORT``,
   ``COMICBOX_ONLINE_CACHE``, ``COMICBOX_ONLINE_CACHE_DIR``,
   ``COMICBOX_ONLINE_CACHE_TTL``, ``COMICBOX_ONLINE_RETRY_BUDGET``.

Both groups are read explicitly here (rather than via confuse's set_env)
so behavior is predictable across nested template depths.
"""

from collections.abc import Mapping
from typing import Any

from comicbox.formats.base.online import SOURCE_NAMES

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

# Per-source credential fields (per ``OnlineSourceCredentials``).
_CRED_FIELDS = ("user", "pass", "key", "url")

# Online settings env-var suffix → resolved field name.
# Keep the field names in sync with the per-knob keys
# ``comicbox.config.online._build_online_settings`` reads from
# ``read_online_env()``.
_BOOL_FIELDS = frozenset({"rematch", "all_sources"})
_FLOAT_FIELDS = frozenset({"auto_threshold"})
_INT_FIELDS = frozenset({"retry_budget"})
_STRING_FIELDS = frozenset(
    {"match", "prompts", "effort", "cache", "cache_dir", "cache_ttl"}
)
_ALL_FIELDS = _BOOL_FIELDS | _FLOAT_FIELDS | _INT_FIELDS | _STRING_FIELDS


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
    Read per-source credentials from ``COMICBOX_<SOURCE>_<FIELD>`` vars.

    Returns a dict mapping source name → field dict, omitting any source
    or field that has no env var set. Field names match
    ``OnlineSourceCredentials`` attributes.
    """
    result: dict[str, dict[str, str]] = {}
    for source in SOURCE_NAMES:
        for cred_field in _CRED_FIELDS:
            env_name = f"COMICBOX_{source.upper()}_{cred_field.upper()}"
            value = env.get(env_name)
            if value is None:
                continue
            result.setdefault(source, {})[cred_field] = value
    return result


def read_online_env(env: Mapping[str, str]) -> dict[str, Any]:
    """
    Read online lookup / cache / tuning settings from ``COMICBOX_ONLINE_*`` vars.

    Returns a dict keyed by resolved field name; missing env vars are
    omitted. Booleans, floats, and ints are parsed; strings are returned
    as-is. Unparseable values are dropped.
    """
    result: dict[str, Any] = {}
    for field_name in _ALL_FIELDS:
        raw = env.get(f"COMICBOX_ONLINE_{field_name.upper()}")
        if raw is None:
            continue
        if field_name in _BOOL_FIELDS:
            parsed_bool = parse_bool(raw)
            if parsed_bool is not None:
                result[field_name] = parsed_bool
        elif field_name in _FLOAT_FIELDS:
            try:
                result[field_name] = float(raw)
            except ValueError:
                continue
        elif field_name in _INT_FIELDS:
            try:
                result[field_name] = int(raw)
            except ValueError:
                continue
        else:
            result[field_name] = raw
    return result
