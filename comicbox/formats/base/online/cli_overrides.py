"""
Parse the repeatable per-source CLI ``--auth`` overrides.

The CLI flag ``--auth`` is repeatable. ``<source>:<token>`` sets that
source's API token; ``<source>:<field>=<value>`` sets a named field.
Each occurrence is collected and turned into a per-source field dict
the credential resolver consumes.

Examples:
    --auth metron:abcdef0123456789
    --auth comicvine:ABCD1234
    --auth comicvine:key=ABCD1234
    --auth comicvine:url=https://comicvine.gamespot.com/api

``url`` overrides a source's API endpoint. Only ComicVine honors it;
mokkari has no base-URL override, so Metron warns and ignores it.

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from comicbox.exceptions import ConfigurationError
from comicbox.formats.base.online import SOURCE_NAMES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Self

_VALID_AUTH_FIELDS = frozenset({"key", "url"})


def _parse_auth_field(label: str, source: str, rest: str) -> tuple[str, str]:
    """
    Split an entry's post-source remainder into a field and a value.

    No error here or in `_parse_auth_entry` repeats anything typed after
    the source name, nor an unknown source name: a user who forgets
    ``key=`` puts the token where the field name goes, base64-style
    tokens end in ``=``, and the doctor's report promises never to carry
    one. They name the entry's position and what is valid instead.
    """
    cred_field, sep, value = rest.partition("=")
    if not sep:
        # Bare `<source>:<token>` shorthand: the API token is the field
        # users reach for, so it needs no name. Tokens are hex or JWT and
        # so never contain "=", which keeps this unambiguous.
        return "key", rest
    cred_field = cred_field.strip().lower()
    if cred_field not in _VALID_AUTH_FIELDS:
        reason = (
            f"{label}: unknown field for {source}; "
            f"valid: {', '.join(sorted(_VALID_AUTH_FIELDS))}"
        )
        raise ConfigurationError(reason)
    return cred_field, value


def _parse_auth_entry(position: int, raw: str) -> tuple[str, str, str]:
    """Parse a single ``<source>:<token>`` or ``<source>:<field>=<value>`` entry."""
    label = f"--auth entry {position}"
    source, sep, rest = raw.partition(":")
    if not sep:
        reason = (
            f"{label}: has no source; use <source>:<token> or <source>:<field>=<value>"
        )
        raise ConfigurationError(reason)
    source = source.strip().lower()
    if source not in SOURCE_NAMES:
        reason = f"{label}: unknown source; known: {', '.join(SOURCE_NAMES)}"
        raise ConfigurationError(reason)
    cred_field, value = _parse_auth_field(label, source, rest)
    if not value:
        reason = f"{label}: empty value for {source} {cred_field}"
        raise ConfigurationError(reason)
    return source, cred_field, value


@dataclass(frozen=True, slots=True)
class CliOverrides:
    """
    CLI flag values for per-source credentials.

    ``per_source`` maps source name → {field_name: value}. Only fields
    explicitly provided on the CLI appear; missing fields fall through
    to env/config.
    """

    per_source: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def from_auth_list(cls, entries: Iterable[str]) -> Self:
        """Build from a list of parsed ``--auth`` strings."""
        per_source: dict[str, dict[str, str]] = {}
        for position, raw in enumerate(entries or (), start=1):
            if not raw:
                continue
            source, cred_field, value = _parse_auth_entry(position, raw)
            per_source.setdefault(source, {})[cred_field] = value
        return cls(per_source={k: dict(v) for k, v in per_source.items()})
