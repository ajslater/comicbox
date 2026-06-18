"""
Parse the repeatable per-source CLI ``--auth`` overrides.

The CLI flag ``--auth`` is repeatable with the form
``<source>:<field>=<value>``. Each occurrence is collected and turned
into a per-source field dict the credential resolver consumes.

Examples:
    --auth metron:user=AJSlater
    --auth metron:pass='hunter2'
    --auth metron:url=https://metron.cloud
    --auth comicvine:key=ABCD1234
    --auth comicvine:url=https://comicvine.gamespot.com/api

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from comicbox.formats.base.online import SOURCE_NAMES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_VALID_AUTH_FIELDS = frozenset({"user", "pass", "key", "url"})


def _parse_auth_entry(raw: str) -> tuple[str, str, str]:
    """Parse a single ``<source>:<field>=<value>`` entry."""
    if ":" not in raw or "=" not in raw:
        reason = f"--auth expects <source>:<field>=<value>, got {raw!r}"
        raise ValueError(reason)
    head, _, value = raw.partition("=")
    source, _, cred_field = head.partition(":")
    source = source.strip().lower()
    cred_field = cred_field.strip().lower()
    if source not in SOURCE_NAMES:
        reason = f"--auth: unknown source {source!r}; known: {', '.join(SOURCE_NAMES)}"
        raise ValueError(reason)
    if cred_field not in _VALID_AUTH_FIELDS:
        reason = (
            f"--auth: unknown field {cred_field!r}; "
            f"valid: {', '.join(sorted(_VALID_AUTH_FIELDS))}"
        )
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
