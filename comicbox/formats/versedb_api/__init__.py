"""
VerseDB online API format package.

Schema, transform, the `versedb` SDK adapter and the VerseDBOnlineSource
wrapper live here. The online-tagging infrastructure (matcher, retry,
etc.) remains under `comicbox.formats.base.online.*`.

VerseDB's terms ask for a linked "Data from VerseDB" credit wherever its
data is shown, which is what ``attribution`` carries.
"""

from types import MappingProxyType

from comicbox.formats._base import (
    FormatRegistration,
    MetadataFormat,
    OnlineSourceCliInfo,
)
from comicbox.formats.versedb_api.transform import WEBSITE, VerseDBApiTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "VerseDB API",
        frozenset({"versedb-api", "versedbapi"}),
        "versedb-api.json",
        VerseDBApiTransform,
        lexer="json",
        enabled=False,
    ),
    sources=MappingProxyType(
        {
            "VERSEDB_API": 0,
        }
    ),
    is_online=True,
    cli_info=OnlineSourceCliInfo(
        short_name="versedb",
        credentials="API token",
        id_form="versedb:NNN",
        website=WEBSITE,
        attribution="Data from VerseDB",
    ),
)
