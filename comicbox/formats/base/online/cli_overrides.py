"""
Parse the repeatable per-source CLI ``--auth`` overrides.

The CLI flag ``--auth`` is repeatable. ``<source>:<token>`` sets that
source's API token; ``<source>:<field>=<value>`` sets a named field.
Each occurrence is collected and turned into a per-source field dict
the credential resolver consumes.

Metron's ``user``/``pass`` are deprecated in favor of its API token.

Examples:
    --auth metron:abcdef0123456789
    --auth comicvine:ABCD1234
    --auth metron:user=AJSlater
    --auth metron:pass='hunter2'
    --auth metron:url=https://metron.cloud
    --auth comicvine:url=https://comicvine.gamespot.com/api

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from comicbox.formats.base.online import SOURCE_NAMES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_VALID_AUTH_FIELDS = frozenset({"user", "pass", "key", "url"})


def _parse_auth_field(raw: str, rest: str) -> tuple[str, str]:
    """Split an entry's post-source remainder into a field and a value."""
    cred_field, sep, value = rest.partition("=")
    if not sep:
        # Bare `<source>:<token>` shorthand: the API token is the field
        # users reach for, so it needs no name. Tokens are hex or JWT and
        # so never contain "=", which keeps this unambiguous.
        return "key", rest
    cred_field = cred_field.strip().lower()
    if cred_field not in _VALID_AUTH_FIELDS:
        reason = (
            f"--auth: unknown field {cred_field!r} in {raw!r}; "
            f"valid: {', '.join(sorted(_VALID_AUTH_FIELDS))}"
        )
        raise ValueError(reason)
    return cred_field, value


def _parse_auth_entry(raw: str) -> tuple[str, str, str]:
    """Parse a single ``<source>:<token>`` or ``<source>:<field>=<value>`` entry."""
    source, sep, rest = raw.partition(":")
    if not sep:
        reason = (
            f"--auth expects <source>:<token> or <source>:<field>=<value>, got {raw!r}"
        )
        raise ValueError(reason)
    source = source.strip().lower()
    if source not in SOURCE_NAMES:
        reason = f"--auth: unknown source {source!r}; known: {', '.join(SOURCE_NAMES)}"
        raise ValueError(reason)
    cred_field, value = _parse_auth_field(raw, rest)
    if not value:
        reason = f"--auth: empty value in {raw!r}"
        raise ValueError(reason)
    return source, cred_field, value


@dataclass(frozen=True, slots=True)
class CliOverrides:
    """
    CLI flag values for per-source credentials.

    ``per_source`` maps source name → {field_name: value}. Only fields
    explicitly provided on the CLI appear; missing fields fall through
    to env/config/keyring.
    """

    per_source: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def from_auth_list(cls, entries: Iterable[str]) -> CliOverrides:
        """Build from a list of parsed ``--auth`` strings."""
        per_source: dict[str, dict[str, str]] = {}
        for raw in entries or ():
            if not raw:
                continue
            source, cred_field, value = _parse_auth_entry(raw)
            per_source.setdefault(source, {})[cred_field] = value
        return cls(per_source={k: dict(v) for k, v in per_source.items()})
