"""
Credential resolution chain for online sources.

Resolution order, per (source, field):

1. CLI override (`--api-key DB:KEY`, `--api-user DB:USER`,
   `--api-password DB:PASS`, `--api-url DB:URL`).
2. Environment variable (`COMICBOX_<SOURCE>_<FIELD>`).
3. Config file value (loaded by confuse into the `online.<source>.*` block).
4. Keyring lookup (passwords only, optional dependency, never written by
   comicbox).

Outputs an `OnlineSourceCredentials` instance per source. A source is
"configured" iff its required fields resolve to non-null values; that
check lives on the source class.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from loguru import logger

from comicbox.config.settings import OnlineSourceCredentials
from comicbox.formats.base.online import SOURCE_NAMES
from comicbox.formats.base.online.env import read_credential_env

if TYPE_CHECKING:
    from collections.abc import Mapping

    from comicbox.formats.base.online.cli_overrides import CliOverrides

_FIELDS = ("api_key", "username", "password", "url")
_PW = "password"


def _try_keyring(source: str, username: str | None) -> str | None:
    """
    Look up a password in the system keyring.

    Returns None if `keyring` isn't installed or the entry isn't set.
    Never writes to the keyring; users manage entries out-of-band.
    """
    if not username:
        return None
    try:
        import keyring
    except ImportError:
        return None
    service = f"comicbox-{source}"
    try:
        return keyring.get_password(service, username)
    except Exception as exc:
        logger.debug(f"keyring lookup failed for {service}/{username}: {exc}")
        return None


def _coalesce(*values: str | None) -> str | None:
    """First non-null/non-empty wins."""
    for v in values:
        if v:
            return v
    return None


def resolve_credentials(
    config_creds: Mapping[str, Mapping[str, Any]],
    cli_overrides: CliOverrides | None = None,
    env: Mapping[str, str] | None = None,
    *,
    use_keyring: bool = True,
) -> dict[str, OnlineSourceCredentials]:
    """
    Build the resolved per-source credentials map.

    `config_creds` is the post-confuse view of `online.<source>.*` (file +
    confuse env-var auto-loading). `cli_overrides` is the parsed CLI
    `--api-*` flags. `env` defaults to `os.environ`.
    """
    if env is None:
        env = os.environ
    env_creds = read_credential_env(env)
    cli_creds: Mapping[str, Mapping[str, Any]] = (
        cli_overrides.per_source if cli_overrides else {}
    )

    resolved: dict[str, OnlineSourceCredentials] = {}
    for source in SOURCE_NAMES:
        config_block = dict(config_creds.get(source) or {})
        env_block = env_creds.get(source, {})
        cli_block = dict(cli_creds.get(source) or {})

        values: dict[str, str | None] = {
            field: _coalesce(
                cli_block.get(field),
                env_block.get(field),
                config_block.get(field),
            )
            for field in _FIELDS
        }

        if use_keyring and not values[_PW] and (username := values["username"]):
            values[_PW] = _try_keyring(source, username)

        resolved[source] = OnlineSourceCredentials(**values)
    return resolved
