"""
Metron online API format package.

Schema, transform, and the MetronOnlineSource wrapper live here. The
online-tagging infrastructure (matcher, rate limits, retry, etc.)
remains under `comicbox.online.*`.
"""

from types import MappingProxyType

from comicbox.formats._base import (
    FormatRegistration,
    MetadataFormat,
    OnlineSourceCliInfo,
)
from comicbox.formats.metron_api.transform import MetronApiTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "Metron API",
        frozenset({"metron-api", "metronapi"}),
        "metron-api.json",
        MetronApiTransform,
        lexer="json",
        enabled=False,
    ),
    sources=MappingProxyType(
        {
            "METRON_API": 0,
        }
    ),
    is_online=True,
    cli_info=OnlineSourceCliInfo(
        short_name="metron",
        credentials="username + password",
        id_form="metron:NNN",
        website="https://metron.cloud",
    ),
)
