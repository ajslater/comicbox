"""Identifier consts."""

import re
from enum import Enum
from sys import maxsize
from types import MappingProxyType

from bidict import frozenbidict


class IdSources(Enum):
    """Comic Database Namespace Identifiers."""

    # Comic DBs
    METRON = "metron"
    COMICVINE = "comicvine"
    GCD = "grandcomicsdatabase"
    LCG = "leagueofcomicgeeks"
    MARVEL = "marvel"
    PANELSYNDICATE = "panelsyndicate"
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


_ALL_ID_SOURCES = (
    *ID_SOURCE_VALUES,
    *(id_source.value for id_source in AlternateIdSources),
)
IDENTIFIER_RE_EXP = (
    r"(?P<id_source>" + r"|".join(_ALL_ID_SOURCES) + r"):?(?P<id_key>[\w-]+)"
)
COMICVINE_LONG_ID_KEY_EXP = r"(?P<id_type>\d{4})-(?P<id_key>\d+)"
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
        IdSources.PANELSYNDICATE.value: "Panel Syndicate",
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

ID_SOURCE_ALIASES = MappingProxyType(
    {
        IdSources.ANILIST.value: frozenset({"anilist.co"}),
        IdSources.ASIN.value: frozenset({"amazon.com"}),
        IdSources.COMICVINE.value: frozenset(
            {
                AlternateIdSources.CVDB_ALTERNATE.value,
                "comicvine.gamespot.com",
                "comicvine.com",
            }
        ),
        IdSources.COMIXOLOGY.value: frozenset(
            {"comixology.com", AlternateIdSources.CMXDB_ALTERNATE.value}
        ),
        IdSources.GCD.value: frozenset({"comics.org"}),
        IdSources.GTIN.value: frozenset(
            {"gs1.org", "gs1us.org", "gtinlookup.info", "gtinlookup.org"}
        ),
        IdSources.ISBN.value: frozenset({"isbnsearch.org", "isbndb.com"}),
        IdSources.KITSU.value: frozenset({"kistu.app"}),
        IdSources.LCG.value: frozenset({"leagueofcomicgeeks.com"}),
        IdSources.MANGADEX.value: frozenset({"mangadex.org"}),
        IdSources.MANGAUPDATES.value: frozenset({"mangaupdates.com"}),
        IdSources.MARVEL.value: frozenset({"marvel.com"}),
        IdSources.METRON.value: frozenset({"metron.cloud"}),
        IdSources.MYANIMELIST.value: frozenset({"myanimelist.net"}),
        IdSources.PANELSYNDICATE.value: frozenset({"panelsyndicate.com"}),
        IdSources.UPC.value: frozenset({"barcodelookup.com", "go-upc.com"}),
    }
)

ID_SOURCE_ALIAS_TO_SOURCE_MAP = MappingProxyType(
    {
        alias.lower(): id_source
        for id_source, aliases in ID_SOURCE_ALIASES.items()
        for alias in aliases | {id_source, ID_SOURCE_NAME_MAP[id_source]}
    }
)


def get_id_source_by_alias(id_source_alias: str):
    """Get id source by alias."""
    return ID_SOURCE_ALIAS_TO_SOURCE_MAP.get(id_source_alias.lower(), DEFAULT_ID_SOURCE)


def _build_source_alias_tree(node, source_value, parts):
    part = parts[0]
    if len(parts) == 1:
        node[part] = IdSources(source_value)
    else:
        if part not in node:
            node[part] = {}
        _build_source_alias_tree(node[part], source_value, parts[1:])


def _create_source_alias_tree():
    tree = {}
    for source_value, aliases in ID_SOURCE_ALIASES.items():
        for alias in aliases:
            parts = alias.split(".")
            if len(parts) <= 1:
                continue
            parts.reverse()
            _build_source_alias_tree(tree, source_value, parts)
    return tree


SOURCE_ALIAS_TREE = _create_source_alias_tree()

ID_SOURCES_RANK: MappingProxyType[str, int] = MappingProxyType(
    {enum.value: index for index, enum in enumerate(IdSources)}
)


def compare_identifier_source(
    id_source_a: IdSources | str | None, id_source_b: IdSources | str | None
):
    """Compare identifier sources by string."""
    if isinstance(id_source_a, IdSources):
        id_source_a = id_source_a.value
    else:
        id_source_a = id_source_a.lower() if id_source_a else ""

    if isinstance(id_source_b, IdSources):
        id_source_b = id_source_b.value
    else:
        id_source_b = id_source_b.lower() if id_source_b else ""

    id_source_a_rank = ID_SOURCES_RANK.get(id_source_a, maxsize)
    id_source_b_rank = ID_SOURCES_RANK.get(id_source_b, maxsize)

    return id_source_a_rank > id_source_b_rank
