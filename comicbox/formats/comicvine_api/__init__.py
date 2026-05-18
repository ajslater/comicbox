"""
ComicVine online API format package.

Schema, transform, and the ComicVineOnlineSource wrapper live here. The
online-tagging infrastructure (matcher, rate limits, retry, etc.)
remains under `comicbox.online.*`.
"""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
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
)
