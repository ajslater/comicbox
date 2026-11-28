"""
Credential resolution chain for online sources.

Resolution order, per (source, field):

1. CLI override via ``--auth <source>:<field>=<value>``.
2. The confuse ``online.auth.<source>.*`` block, which already layers
   env vars (``COMICBOX_ONLINE__AUTH__METRON__KEY``) over config files.

Outputs an `OnlineSourceCredentials` instance per source. A source is
"configured" iff its required fields resolve to non-null values; that
check lives on the source class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from comicbox.config.online.settings import OnlineSourceCredentials
from comicbox.formats.base.online import SOURCE_NAMES

if TYPE_CHECKING:
    from collections.abc import Mapping

    from comicbox.formats.base.online.cli_overrides import CliOverrides

_FIELDS = ("key", "url")


def _coalesce(*values: str | None) -> str | None:
    """First non-null/non-empty wins."""
    for v in values:
        if v:
            return v
    return None


def resolve_credentials(
    config_creds: Mapping[str, Mapping[str, Any]],
    cli_overrides: CliOverrides | None = None,
) -> dict[str, OnlineSourceCredentials]:
    """
    Build the resolved per-source credentials map.

    `config_creds` is the post-confuse view of `online.auth.<source>.*`,
    which already layers env vars over config files. `cli_overrides` is
    the parsed `--auth` flags.
    """
    cli_creds: Mapping[str, Mapping[str, Any]] = (
        cli_overrides.per_source if cli_overrides else {}
    )

    resolved: dict[str, OnlineSourceCredentials] = {}
    for source in SOURCE_NAMES:
        config_block = dict(config_creds.get(source) or {})
        cli_block = dict(cli_creds.get(source) or {})

        resolved[source] = OnlineSourceCredentials(
            **{
                field: _coalesce(cli_block.get(field), config_block.get(field))
                for field in _FIELDS
            }
        )
    return resolved
