"""
The dataclass defaults and ``config_default.yaml`` must not drift apart.

comicbox declares every default twice: once as a ``ComicboxSettings``
dataclass default and once in ``config_default.yaml``. The YAML wins at
runtime (``get_config`` builds from the confuse view), so a dataclass
default that disagrees is a silent lie — it only surfaces for code that
constructs the dataclass directly.

That is exactly how ``OnlineTuningSettings.auto_threshold`` ended up at
0.85 while the YAML, the ``--auto-threshold`` help text, and the
matcher's own constant all said 0.95 — and, through a second constant
that mirrored it by hand, dropped the solo-viable auto-write floor to a
value Phase E was written to forbid. That mirror is gone:
``resolve_solo_threshold`` reads the source's resolved
``auto_threshold``, and the test below pins the coupling.

This test walks the two trees together in both directions:

* every YAML key must have a dataclass field, with an equal default;
* every dataclass field must have a YAML key, unless it's declared
  below as runtime-only or structural.

Two normalizations keep it about *values* rather than spelling:
enums/paths/collections are reduced to comparable primitives, and any
two "empty" defaults agree (``null`` vs ``False`` vs ``""`` vs ``[]``).
Numbers are never empty, so ``0.85`` vs ``0.95`` still fails.

Both exception maps are checked for staleness: fix a divergence without
deleting its entry here and this test fails, so the lists can't rot into
a permanent excuse.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from comicbox.config.online.build import _parse_ttl
from comicbox.config.online.settings import OnlineSettings
from comicbox.config.settings import (
    ComicboxSettings,
    ComputeSettings,
    ConvertSettings,
    GeneralSettings,
    PrintSettings,
    ReadSettings,
    WriteSettings,
)
from comicbox.version import PACKAGE_NAME

_DEFAULT_YAML_PATH = Path("comicbox/config_default.yaml")

# Every group dataclass instantiated bare — this is the "what a
# ComicboxSettings believes by itself" side of the comparison. A new
# group without full defaults breaks here, on purpose.
_DEFAULTS = ComicboxSettings(
    general=GeneralSettings(),
    read=ReadSettings(),
    write=WriteSettings(),
    print=PrintSettings(),
    convert=ConvertSettings(),
    compute=ComputeSettings(),
    online=OnlineSettings(),
)

# YAML key -> dataclass field name, where they can't match.
_FIELD_ALIASES = {"read.except": "except_formats"}

# Paths whose YAML text needs decoding before comparison.
_VALUE_DECODERS = {"online.cache.ttl": _parse_ttl}

# YAML keys whose dataclass default deliberately differs. Keep the
# reason; drop the entry when the divergence goes away.
_KNOWN_DIVERGENCES = {
    "read.formats": (
        "The YAML enumerates the nine formats read by default. The "
        "dataclass can't: MetadataFormats is a TYPE_CHECKING-only import "
        "in settings.py (importing it for real would cycle through "
        "comicbox.formats), so the field defaults to an empty frozenset "
        "and the YAML is the only source of the real list."
    ),
    "online.auth": (
        "Structural, not a value difference: the YAML nests one block "
        "per source (metron:, comicvine:), the dataclass holds a single "
        "OnlineAuthSettings.sources mapping keyed by source name. "
        "test_no_credentials_are_defaulted_in_yaml covers the leaves."
    ),
}

# Dataclass fields with no YAML key, and why they don't need one.
_NO_YAML_KEY = {
    "online.lookup.enabled": "Runtime-only: set by --online, never persisted.",
    "online.lookup.ids": "Runtime-only: set by --id.",
    "online.lookup.series_ids": "Runtime-only: set by --series-id.",
    "online.auth.sources": "See the online.auth divergence note above.",
    "all_write_formats": "Computed by compute_config().",
    "read_filename_formats": "Computed by compute_config().",
    "read_file_formats": "Computed by compute_config().",
    "read_metadata_lower_filenames": "Computed by compute_config().",
    "is_read_comments": "Computed by compute_config().",
    "is_skip_computed_from_tags": "Computed by compute_config().",
}


def _load_yaml_defaults() -> dict[str, Any]:
    with _DEFAULT_YAML_PATH.open(encoding="utf-8") as yaml_file:
        return yaml.safe_load(yaml_file)[PACKAGE_NAME]


def _is_empty(value: Any) -> bool:
    """Treat every flavor of "unset" as the same. Numbers are never empty."""
    if value is None or value is False:
        return True
    return (
        isinstance(value, str | tuple | list | set | frozenset | Mapping) and not value
    )


def _normalize(value: Any) -> Any:
    """Reduce a default to something comparable across YAML and Python."""
    if _is_empty(value):
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, set | frozenset | tuple | list):
        return tuple(sorted(str(_normalize(item)) for item in value))
    # str / bool / int / float / timedelta compare as themselves.
    return value


def _walk(yaml_node: Mapping[str, Any], settings: Any, prefix: str = "") -> None:
    """Compare one YAML mapping against the dataclass that mirrors it."""
    field_names = {f.name for f in fields(settings)}
    seen: set[str] = set()

    for key, yaml_value in yaml_node.items():
        path = f"{prefix}{key}"
        if path in _KNOWN_DIVERGENCES:
            # Still record the field so the reverse check stays honest.
            seen.add(_FIELD_ALIASES.get(path, key))
            continue
        name = _FIELD_ALIASES.get(path, key)
        assert name in field_names, (
            f"{path}: config_default.yaml declares a key with no "
            f"ComicboxSettings field. Add the field or drop the key."
        )
        seen.add(name)
        value = getattr(settings, name)
        if is_dataclass(value) and isinstance(yaml_value, Mapping):
            _walk(yaml_value, value, f"{path}.")
            continue
        decoder = _VALUE_DECODERS.get(path)
        decoded = decoder(yaml_value) if decoder else yaml_value
        assert _normalize(decoded) == _normalize(value), (
            f"{path}: config_default.yaml says {yaml_value!r} but the "
            f"dataclass default is {value!r}. The YAML wins at runtime, so "
            f"the dataclass is lying to anyone who builds it directly."
        )

    for name in field_names - seen:
        path = f"{prefix}{name}"
        assert path in _NO_YAML_KEY, (
            f"{path}: ComicboxSettings field with no config_default.yaml "
            f"key. Add the key, or declare it in _NO_YAML_KEY with a reason."
        )


def test_dataclass_defaults_match_yaml_defaults() -> None:
    """Every shared default agrees, in both directions."""
    _walk(_load_yaml_defaults(), _DEFAULTS)


def test_auto_threshold_default_agrees_everywhere() -> None:
    """
    The specific drift that motivated this file, pinned by name.

    The generic walk above covers it, but this failure message is the
    one worth reading when someone edits a threshold.
    """
    from comicbox.config.online.settings import (
        DEFAULT_AUTO_THRESHOLD,
        OnlineSettings,
        OnlineSourceTuning,
        OnlineTuningSettings,
        resolve_auto_threshold,
        resolve_solo_threshold,
    )

    yaml_value = _load_yaml_defaults()["online"]["tuning"]["auto_threshold"]
    assert OnlineTuningSettings().auto_threshold == DEFAULT_AUTO_THRESHOLD
    assert yaml_value == DEFAULT_AUTO_THRESHOLD
    # Phase E's solo-viable floor is defined as "the same bar as a
    # multi-candidate unambiguous win". Below it, a lone mediocre
    # candidate auto-writes silently — so it tracks the threshold this
    # source actually runs at, for every way of setting one.
    for settings in (
        OnlineSettings(),
        OnlineSettings(tuning=OnlineTuningSettings(auto_threshold=0.99)),
        OnlineSettings(tuning=OnlineTuningSettings(auto_threshold=0.70)),
        OnlineSettings(
            tuning=OnlineTuningSettings(
                per_source={"metron": OnlineSourceTuning(auto_threshold=0.98)}
            )
        ),
    ):
        assert resolve_solo_threshold(settings, "metron") == resolve_auto_threshold(
            settings, "metron"
        )
    # An explicit per-source solo_threshold still wins.
    opted_in = OnlineSettings(
        tuning=OnlineTuningSettings(
            per_source={"metron": OnlineSourceTuning(solo_threshold=0.50)}
        )
    )
    assert resolve_solo_threshold(opted_in, "metron") == 0.50


def test_no_credentials_are_defaulted_in_yaml() -> None:
    """The auth blocks are exempt from the walk, so check them directly."""
    auth = _load_yaml_defaults()["online"]["auth"]
    for source, block in auth.items():
        for key, value in block.items():
            assert value is None, (
                f"online.auth.{source}.{key} ships a non-null default "
                f"({value!r}). Credentials must never have one."
            )


def test_divergence_exceptions_are_not_stale() -> None:
    """
    Every declared exception must still describe a real divergence.

    Without this, fixing a drift leaves a dead entry behind that would
    hide the next one at the same path.
    """
    yaml_defaults = _load_yaml_defaults()
    for path in _KNOWN_DIVERGENCES:
        node: Any = yaml_defaults
        settings: Any = _DEFAULTS
        parts = path.split(".")
        for part in parts[:-1]:
            node = node[part]
            settings = getattr(settings, part)
        leaf = parts[-1]
        assert leaf in node, f"{path}: declared as divergent but gone from the YAML."
        name = _FIELD_ALIASES.get(path, leaf)
        if not hasattr(settings, name):
            continue  # structural: no field to compare against.
        yaml_value = node[leaf]
        value = getattr(settings, name)
        if is_dataclass(value) and isinstance(yaml_value, Mapping):
            continue  # structural subtree.
        assert _normalize(yaml_value) != _normalize(value), (
            f"{path}: no longer diverges. Delete its _KNOWN_DIVERGENCES entry."
        )


def test_no_yaml_key_exceptions_are_not_stale() -> None:
    """A field listed as YAML-less must really be absent from the YAML."""
    yaml_defaults = _load_yaml_defaults()
    for path in _NO_YAML_KEY:
        node: Any = yaml_defaults
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.get(part, {})
        assert parts[-1] not in node, (
            f"{path}: now has a config_default.yaml key. Delete its "
            f"_NO_YAML_KEY entry so its default gets compared."
        )
