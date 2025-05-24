"""Identifier consts."""

import re
from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

ID_KEY_KEY = "id_key"
URL_KEY = "url"


class IdSources(Enum):
    """Comic Database Namespace Identifiers."""

    # Comic DBs
    METRON = "metron"
    COMICVINE = "comicvine"
    GCD = "grandcomicsdatabase"
    LCG = "leagueofcomicgeeks"
    MARVEL = "marvel"
    # Manga DBs
    ANILIST = "anilist"
    KITSU = "kitsu"
    MANGADEX = "mangadex"
    MANGAUPDATES = "mangaupdates"
    MYANIMELIST = "myanimelist"
    # GTINs
    GTIN = "gtin"
    ISBN = "isbn"
    UPC = "upc"
    ASIN = "asin"
    COMIXOLOGY = "comixology"


ID_SOURCE_VALUES = (id_source.value for id_source in IdSources)
DEFAULT_ID_SOURCE = IdSources.COMICVINE.value
DEFAULT_ID_TYPE = "issue"


# Non standard
class AlternateIdSources(Enum):
    """Alternate ID_SOURCE Names."""

    CVDB_ALTERNATE = "cvdb"
    CMXDB_ALTERNATE = "cmxdb"


_ALL_IdSources = (
    *ID_SOURCE_VALUES,
    *(id_source.value for id_source in AlternateIdSources),
)
IDENTIFIER_RE_EXP = (
    r"(?P<id_source>" + r"|".join(_ALL_IdSources) + r"):?(?P<id_key>[\w-]+)"
)
COMICVINE_LONG_ID_KEY_EXP = r"(?P<id_keytype>\d{4})-(?P<id_key>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_ID_KEY_EXP)

ID_SOURCE_NAME_MAP = frozenbidict(
    {
        # DBs
        IdSources.ANILIST.value: "AniList",
        IdSources.COMICVINE.value: "Comic Vine",
        IdSources.COMIXOLOGY.value: "ComiXology",
        IdSources.GCD.value: "Grand Comics Database",
        IdSources.KITSU.value: "Kitsu",
        IdSources.LCG.value: "League of Comic Geeks",
        IdSources.MANGADEX.value: "MangaDex",
        IdSources.MANGAUPDATES.value: "MangaUpdates",
        IdSources.MARVEL.value: "Marvel",
        IdSources.METRON.value: "Metron",
        IdSources.MYANIMELIST.value: "MyAnimeList",
        # GITNs
        IdSources.ASIN.value: "Amazon",
        IdSources.GTIN.value: "GTIN",
        IdSources.ISBN.value: "ISBN",
        IdSources.UPC.value: "UPC",
    }
)

_IDENTIFIER_URN_ID_SOURCE_ALIASES = MappingProxyType(
    {
        IdSources.ANILIST.value: frozenset({"anilist.co"}),
        IdSources.ASIN.value: frozenset({"amazon.com", "www.amazon.com"}),
        IdSources.COMICVINE.value: frozenset(
            {AlternateIdSources.CVDB_ALTERNATE.value, "comicvine.gamespot.org"}
        ),
        IdSources.COMIXOLOGY.value: frozenset(
            {"comixology.com", AlternateIdSources.CMXDB_ALTERNATE.value}
        ),
        IdSources.GCD.value: frozenset({"comics.org"}),
        IdSources.GTIN.value: frozenset({}),
        IdSources.ISBN.value: frozenset({}),
        IdSources.KITSU.value: frozenset({"kistu.app"}),
        IdSources.LCG.value: frozenset({"leagueofcomicgeeks.com"}),
        IdSources.MANGADEX.value: frozenset({"mangadex.org"}),
        IdSources.MANGAUPDATES.value: frozenset({"mangaupdates.com"}),
        IdSources.MARVEL.value: frozenset({"marvel.com"}),
        IdSources.METRON.value: frozenset({"metron.cloud"}),
        IdSources.MYANIMELIST.value: frozenset({"myanimelist.net"}),
        IdSources.UPC.value: frozenset({}),
    }
)

ALIAS_ID_SOURCE_MAP = MappingProxyType(
    {
        alias.lower(): id_source
        for id_source, aliases in _IDENTIFIER_URN_ID_SOURCE_ALIASES.items()
        for alias in aliases | {id_source, ID_SOURCE_NAME_MAP[id_source]}
    }
)
