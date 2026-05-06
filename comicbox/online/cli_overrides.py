"""
Parse the repeatable per-source CLI overrides for online tagging.

The CLI flags `--api-key`, `--api-user`, `--api-password`, and
`--api-url` all take values in the form ``DB:VALUE``. Multiple
occurrences are collected and turned into a per-source field dict the
credential resolver consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from comicbox.online import SOURCE_NAMES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# OnlineSourceCredentials field name → CLI flag suffix (`--api-<suffix>`).
_FIELD_TO_FLAG_SUFFIX: Mapping[str, str] = MappingProxyType(
    {
        "api_key": "key",
        "username": "user",
        "password": "password",
        "url": "url",
    }
)


def _parse_pairs(raw_values: Iterable[str], cli_flag_suffix: str) -> dict[str, str]:
    """Parse a list of ``db:value`` strings into a per-source dict."""
    out: dict[str, str] = {}
    for raw in raw_values:
        if not raw:
            continue
        if ":" not in raw:
            reason = f"--api-{cli_flag_suffix} expects DB:VALUE, got {raw!r}"
            raise ValueError(reason)
        source, _, value = raw.partition(":")
        source = source.strip().lower()
        if source not in SOURCE_NAMES:
            reason = (
                f"unknown online source {source!r}; "
                f"known sources: {', '.join(SOURCE_NAMES)}"
            )
            raise ValueError(reason)
        out[source] = value
    return out


@dataclass(frozen=True, slots=True)
class CliOverrides:
    """
    CLI flag values for per-source credentials.

    `per_source` maps source name → {field_name: value}. Only fields
    explicitly provided on the CLI appear; missing fields fall through
    to env/config/keyring.
    """

    per_source: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def from_cli(
        cls,
        api_keys: Iterable[str] = (),
        api_users: Iterable[str] = (),
        api_passwords: Iterable[str] = (),
        api_urls: Iterable[str] = (),
    ) -> CliOverrides:
        """Build from parsed CLI flag values."""
        per_source: dict[str, dict[str, str]] = {}
        raw_groups: tuple[tuple[str, Iterable[str]], ...] = (
            ("api_key", api_keys),
            ("username", api_users),
            ("password", api_passwords),
            ("url", api_urls),
        )
        for cred_field, values in raw_groups:
            flag_suffix = _FIELD_TO_FLAG_SUFFIX[cred_field]
            for source, value in _parse_pairs(values, flag_suffix).items():
                per_source.setdefault(source, {})[cred_field] = value
        return cls(per_source={k: dict(v) for k, v in per_source.items()})
