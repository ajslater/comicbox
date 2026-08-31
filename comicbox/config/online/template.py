"""Confuse template for the ``online`` config block."""

from pathlib import Path

from confuse.templates import (
    Integer,
    MappingTemplate,
    Number,
    OneOf,
    Optional,
    String,
)

# Any non-Mapping container type — set/frozenset/tuple/list all pass.
# Shared with the rest of the template; compute_config writes frozensets
# into list-typed fields before validation sees them.
NON_MAPPING_TYPES = (set, frozenset, tuple, list)
NON_MAPPING_CONTAINER = OneOf(NON_MAPPING_TYPES)


_RATE_LIMIT_TEMPLATE = MappingTemplate(
    {
        "per_minute": Optional(Integer()),
        "per_day": Optional(Integer()),
        "per_second": Optional(Integer()),
        "per_hour": Optional(Integer()),
    }
)


_PER_SOURCE_TUNING_TEMPLATE = MappingTemplate(
    {
        "auto_threshold": Optional(Number()),
        "effort": Optional(String()),
        "min_confidence": Optional(Number()),
        "disambiguation_margin": Optional(Number()),
        "solo_threshold": Optional(Number()),
        "rate_limit": Optional(_RATE_LIMIT_TEMPLATE),
    }
)


_AUTH_SOURCE_TEMPLATE = MappingTemplate(
    {
        "user": Optional(str),
        "pass": Optional(str),
        "key": Optional(str),
        "url": Optional(str),
    }
)


ONLINE_TEMPLATE = MappingTemplate(
    {
        "lookup": MappingTemplate(
            {
                "match": String(),
                "prompts": String(),
                "rematch": bool,
                # A CSV string is accepted alongside a container so an
                # env var can set it; _normalize_sources splits either.
                "sources": Optional(OneOf((str, *NON_MAPPING_TYPES))),
                "first_wins": bool,
            }
        ),
        "auth": MappingTemplate(
            {
                "metron": _AUTH_SOURCE_TEMPLATE,
                "comicvine": _AUTH_SOURCE_TEMPLATE,
            }
        ),
        "cache": MappingTemplate(
            {
                "mode": String(),
                "dir": Optional(OneOf((str, Path))),
                "ttl": String(),
            }
        ),
        "tuning": MappingTemplate(
            {
                "auto_threshold": Number(),
                "effort": String(),
                "retry_budget": Integer(),
                "per_source": Optional(dict),
            }
        ),
    }
)
