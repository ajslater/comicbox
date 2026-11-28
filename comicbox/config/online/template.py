"""Confuse template for the ``online`` config block."""

from pathlib import Path

from confuse.templates import (
    Integer,
    MappingTemplate,
    MappingValues,
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
# A lifetime: "7d", "24h", "0", or a bare number of seconds.
TTL_TEMPLATE = OneOf((String(), Number()))


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
        # One block per name in `SOURCE_NAMES`, spelled out because this
        # module may not import the formats package. confuse drops keys a
        # template doesn't name, so a source missing here would have its
        # credentials silently ignored; a drift test keeps the two in step.
        "auth": MappingTemplate(
            {
                "metron": _AUTH_SOURCE_TEMPLATE,
                "comicvine": _AUTH_SOURCE_TEMPLATE,
                "versedb": _AUTH_SOURCE_TEMPLATE,
            }
        ),
        "cache": MappingTemplate(
            {
                # A bare on or off is a YAML 1.1 boolean, and a number is
                # let through so the builder can name the valid modes.
                "mode": OneOf((String(), bool, Number())),
                "dir": Optional(OneOf((str, Path))),
                # "7d", or a number of seconds: the docs suggest a bare 0.
                "ttl": TTL_TEMPLATE,
            }
        ),
        "tuning": MappingTemplate(
            {
                "auto_threshold": Number(),
                "effort": Optional(String()),
                "retry_budget": Integer(),
                # Keyed by source name, each block type-checked. A null
                # block (every key commented out) is allowed; the builder
                # skips it and warns about unknown source names.
                "per_source": Optional(
                    MappingValues(Optional(_PER_SOURCE_TUNING_TEMPLATE))
                ),
            }
        ),
    }
)
