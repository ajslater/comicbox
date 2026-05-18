"""
ComicVine online API format package.

Schema, transform, and the ComicVineOnlineSource wrapper live here. The
online-tagging infrastructure (matcher, rate limits, retry, etc.)
remains under `comicbox.formats.base.online.*`.
"""

from types import MappingProxyType

from comicbox.formats._base import (
    FormatRegistration,
    MetadataFormat,
    OnlineSourceCliInfo,
)
from comicbox.formats.comicvine_api.transform import ComicVineApiTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "ComicVine API",
        frozenset({"comicvine-api", "cv-api", "comicvineapi"}),
        "comicvine-api.json",
        ComicVineApiTransform,
        lexer="json",
        enabled=False,
    ),
    sources=MappingProxyType(
        {
            "COMICVINE_API": 0,
        }
    ),
    is_online=True,
    cli_info=OnlineSourceCliInfo(
        short_name="comicvine",
        credentials="api_key",
        id_form="comicvine:NNN  or  comicvine:4000-NNN",
        website="https://comicvine.gamespot.com",
    ),
)
