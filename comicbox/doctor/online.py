"""
Online: each tagging source's credentials, the keyring, and the cache.

Never prints a secret. A credential row names the field and the layer
that supplied it (``--auth``, the env var, the config file, or the
keyring), never the value. Proxy env vars are named, not shown, since a
proxy URL can carry a password.
"""

from __future__ import annotations

import os
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from confuse import Configuration, NotFoundError
from rich.filesize import decimal

from comicbox.doctor.packages import reinstall_hint
from comicbox.doctor.result import CheckResult, Status, short_path
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.version import PACKAGE_NAME

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path

    from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
    from comicbox.doctor.context import Check, DoctorContext

SECTION = "Online"

# The credential fields, under their config and --auth names.
_FIELDS = ("key", "user", "pass", "url")
_KEYRING = "keyring"
_NULL_KEYRING_MODULES = frozenset({"keyring.backends.fail", "keyring.backends.null"})
_PROXY_VARS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "SSL_CERT_FILE",
    }
)

_row = partial(CheckResult, SECTION)


def _env_var(source: str, field: str) -> str:
    return f"{PACKAGE_NAME.upper()}_ONLINE__AUTH__{source.upper()}__{field.upper()}"


def _field_value(creds: OnlineSourceCredentials, field: str) -> str | None:
    return creds.password if field == "pass" else getattr(creds, field)


def _config_layer(view: Any, source: str, field: str) -> str:
    """Name the config layer that supplied one field, or "" if none did."""
    try:
        value, config_source = view[source][field].first()
    except NotFoundError:
        return ""
    if not value:
        return ""
    if filename := getattr(config_source, "filename", None):
        return short_path(filename)
    # read_config_sources mounts the env vars as an anonymous source.
    env_var = _env_var(source, field)
    return f"env {env_var}" if env_var in os.environ else "config"


def _provenance(ctx: DoctorContext) -> dict[str, dict[str, str]]:
    """
    Name the layer that supplied each credential field, per source.

    Mirrors `resolve_credentials`' precedence: ``--auth``, then the config
    tree (env vars over the --config file over the user config), then the
    keyring for a password. Worked out here rather than recorded by the
    resolver, because by the time it runs the config tree has already
    merged env vars and files into one value.
    """
    from comicbox.config.read import read_config_sources
    from comicbox.formats.base.online.cli_overrides import CliOverrides

    config = Configuration(PACKAGE_NAME, modname=PACKAGE_NAME, read=False)
    read_config_sources(config, ctx.args)
    view = config[PACKAGE_NAME]["online"]["auth"]
    flags = CliOverrides.from_auth_list(getattr(ctx.cns, "auth", None) or ()).per_source
    resolved = ctx.settings.online.auth.sources if ctx.settings else {}
    provenance: dict[str, dict[str, str]] = {}
    for source in SOURCE_NAMES:
        layers: dict[str, str] = {}
        for field in _FIELDS:
            if field in flags.get(source, {}):
                layers[field] = "--auth"
            elif layer := _config_layer(view, source, field):
                layers[field] = layer
        creds = resolved.get(source)
        if "pass" not in layers and creds is not None and creds.password:
            layers["pass"] = _KEYRING
        provenance[source] = layers
    return provenance


def _consulted_keyring(provenance: Mapping[str, Mapping[str, str]]) -> list[str]:
    """List the sources with a user and no configured password: the keyring was asked."""
    return [
        source
        for source, layers in provenance.items()
        if "user" in layers and layers.get("pass", _KEYRING) == _KEYRING
    ]


def _metron_warnings(creds: OnlineSourceCredentials) -> Iterator[CheckResult]:
    if not creds.key and creds.user and creds.password:
        yield _row(
            "metron",
            Status.WARN,
            detail="user/pass auth is deprecated",
            fix="use an API token: --auth metron:TOKEN",
        )
    if creds.url:
        yield _row(
            "metron",
            Status.WARN,
            detail="url is ignored: mokkari can't change Metron's URL",
            fix="remove online.auth.metron.url",
        )


def _comicvine_warnings(creds: OnlineSourceCredentials) -> Iterator[CheckResult]:
    if creds.url and creds.url.endswith("/"):
        yield _row(
            "comicvine",
            Status.WARN,
            detail="url ends in /: requests go to //",
            fix="drop the trailing slash",
        )


_SOURCE_WARNINGS: Mapping[
    str, Callable[[OnlineSourceCredentials], Iterator[CheckResult]]
] = MappingProxyType({"metron": _metron_warnings, "comicvine": _comicvine_warnings})


def _comicvine_budget(online: OnlineSettings) -> list[str]:
    """
    Name the scarcest Comic Vine pool's hourly budget, from the bucket file.

    Read-only, and costs no request: the file outlives the runs that spent it.
    """
    from comicbox.formats.comicvine_api.online_source import (
        shared_client_rate_limit_status,
    )

    windows = shared_client_rate_limit_status(online)
    if not windows:
        return []
    pool, window = min(sorted(windows.items()), key=lambda item: item[1]["remaining"])
    budget = f"{window['remaining']}/{window['limit']} left this hour"
    if window["remaining"] == window["limit"]:
        return [f"{budget} in every pool"]
    return [f"{pool} {budget}"]


_SOURCE_NOTES: Mapping[str, Callable[[OnlineSettings], list[str]]] = MappingProxyType(
    {"comicvine": _comicvine_budget}
)


def _source_rows(
    name: str,
    creds: OnlineSourceCredentials,
    layers: Mapping[str, str],
    online: OnlineSettings,
    *,
    configured: bool,
) -> Iterator[CheckResult]:
    if not configured:
        yield _row(
            name,
            Status.OFF,
            detail="no credentials",
            fix=f"--auth {name}:KEY or {_env_var(name, 'key')}",
        )
        return
    present = [field for field in _FIELDS if _field_value(creds, field)]
    notes = [f"{field} from {layers[field]}" for field in present if field in layers]
    if source_notes := _SOURCE_NOTES.get(name):
        notes.extend(source_notes(online))
    yield _row(name, Status.OK, found=", ".join(present), detail=" · ".join(notes))
    if warnings := _SOURCE_WARNINGS.get(name):
        yield from warnings(creds)


def check_sources(ctx: DoctorContext) -> Iterator[CheckResult]:
    """Whether each source has the credentials it needs, and where they came from."""
    if ctx.settings is None:
        yield _row(
            "sources",
            Status.WARN,
            detail="not checked: the config didn't load",
            fix="fix the Config problems above",
        )
        return
    # The run's own source table, so the doctor builds what a run builds.
    from comicbox.box.online_lookup import _DEFAULT_SOURCE_FACTORIES
    from comicbox.config.online.settings import OnlineSourceCredentials

    online = ctx.settings.online
    provenance = _provenance(ctx)
    for name in SOURCE_NAMES:
        creds = online.auth.sources.get(name) or OnlineSourceCredentials()
        source = _DEFAULT_SOURCE_FACTORIES[name](creds, online)
        yield from _source_rows(
            name, creds, provenance[name], online, configured=source.is_configured()
        )


def check_keyring(ctx: DoctorContext) -> Iterator[CheckResult]:
    """
    Report the keyring backend, and warn if a source needs one that can't work.

    comicbox reads the keyring only for a source with a user and no
    password, and loading the config already did that lookup, as a run
    does. The doctor never calls `get_password` itself: macOS can answer
    with a Keychain prompt.
    """
    if ctx.settings is None:
        return
    consulted = _consulted_keyring(_provenance(ctx))
    needed_by = f"{', '.join(consulted)} has a user and no pass"
    try:
        import keyring
    except ImportError:
        if consulted:
            yield _row(
                _KEYRING,
                Status.WARN,
                detail=f"not installed, but {needed_by}",
                fix=reinstall_hint("keyring"),
            )
        else:
            yield _row(_KEYRING, Status.OFF, detail="not installed; not needed")
        return
    backend = keyring.get_keyring()
    found = str(getattr(backend, "name", type(backend).__name__))
    if consulted and type(backend).__module__ in _NULL_KEYRING_MODULES:
        yield _row(
            _KEYRING,
            Status.WARN,
            found=found,
            detail=f"no usable backend, but {needed_by}",
            fix="install a keyring backend, or set the pass",
        )
        return
    notes = [f"priority {getattr(backend, 'priority', '?')}"]
    if consulted:
        notes.append(f"consulted for {', '.join(consulted)}")
    yield _row(_KEYRING, Status.OK, found=found, detail=" · ".join(notes))


def _nearest_existing(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def check_cache(ctx: DoctorContext) -> Iterator[CheckResult]:
    """
    Check that the online cache directory is writable.

    Comic Vine needs it even with ``--cache off``: its rate-limit bucket
    lives there.
    """
    if ctx.settings is None:
        return
    from comicbox.formats.base.online.sources.base import resolve_cache_db_path

    cache_dir = resolve_cache_db_path(
        ctx.settings.online.cache.dir, "doctor", create=False
    ).parent
    existing = _nearest_existing(cache_dir)
    if not os.access(existing, os.W_OK):
        yield _row(
            "cache",
            Status.MISCONFIGURED,
            found=cache_dir,
            detail=f"{short_path(existing)} isn't writable",
            fix="point --cache-dir or online.cache.dir somewhere writable",
        )
        return
    try:
        import sqlite3
    except ImportError:
        yield _row(
            "cache",
            Status.MISSING,
            found=cache_dir,
            detail="no sqlite3: no response cache or Comic Vine rate limiting",
            fix="use a Python built with sqlite3",
        )
        return
    if existing == cache_dir:
        size = sum(
            path.stat().st_size for path in cache_dir.rglob("*") if path.is_file()
        )
        notes = ["writable", decimal(size)]
    else:
        notes = ["not created yet", "parent writable"]
    notes.append(f"sqlite {sqlite3.sqlite_version}")
    yield _row("cache", Status.OK, found=cache_dir, detail=" · ".join(notes))


def check_proxy(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Name the proxy and CA env vars that will steer online requests."""
    if names := [name for name in sorted(os.environ) if name.upper() in _PROXY_VARS]:
        yield _row("proxy", Status.OK, detail=f"set: {', '.join(names)}")


CHECKS: tuple[Check, ...] = (
    (SECTION, "sources", check_sources),
    (SECTION, _KEYRING, check_keyring),
    (SECTION, "cache", check_cache),
    (SECTION, "proxy", check_proxy),
)
