"""Identifier maps."""

from types import MappingProxyType

from bidict import frozenbidict

from comicbox.enums.comicbox import AlternateIdSources, IdSources
from comicbox.identifiers import DEFAULT_ID_SOURCE

ID_SOURCE_NAME_MAP: frozenbidict[IdSources, str] = frozenbidict(
    {
        # DBs
        IdSources.ANILIST: "AniList",
        IdSources.COMICVINE: "Comic Vine",
        IdSources.COMIXOLOGY: "ComiXology",
        IdSources.GCD: "Grand Comics Database",
        IdSources.KITSU: "Kitsu",
        IdSources.LCG: "League of Comic Geeks",
        IdSources.PANELSYNDICATE: "Panel Syndicate",
        IdSources.MANGADEX: "MangaDex",
        IdSources.MANGAUPDATES: "MangaUpdates",
        IdSources.MARVEL: "Marvel",
        IdSources.METRON: "Metron",
        IdSources.MYANIMELIST: "MyAnimeList",
        # GITNs
        IdSources.ASIN: "Amazon",
        IdSources.GTIN: "GTIN",
        IdSources.ISBN: "ISBN",
        IdSources.UPC: "UPC",
    }
)

_ID_SOURCE_ALIASES: MappingProxyType[IdSources, frozenset[str]] = MappingProxyType(
    {
        IdSources.ANILIST: frozenset({"anilist.co"}),
        IdSources.ASIN: frozenset(
            {
                "amazon.com",
                "amazon.ca",
                "amazon.co.uk",
                "amazon.co.jp",
                "amazon.com.mx",
                "amazon.com.br",
                "amazon.es",
                "amazon.de",
                "amazon.fr",
                "amazon.it",
            }
        ),
        IdSources.COMICVINE: frozenset(
            {
                AlternateIdSources.CVDB_ALTERNATE.value,
                "comicvine.gamespot.com",
                "comicvine.com",
                "www.comicvine.com",
                "stage.comicvine.com",
                "www.stage.comicvine.com",
            }
        ),
        IdSources.COMIXOLOGY: frozenset(
            {"comixology.com", AlternateIdSources.CMXDB_ALTERNATE.value}
        ),
        IdSources.GCD: frozenset({"comics.org"}),
        IdSources.GTIN: frozenset(
            {"gs1.org", "gs1us.org", "gtinlookup.info", "gtinlookup.org"}
        ),
        IdSources.ISBN: frozenset({"isbnsearch.org", "isbndb.com"}),
        IdSources.KITSU: frozenset({"kistu.app"}),
        IdSources.LCG: frozenset({"leagueofcomicgeeks.com"}),
        IdSources.MANGADEX: frozenset({"mangadex.org"}),
        IdSources.MANGAUPDATES: frozenset({"mangaupdates.com"}),
        IdSources.MARVEL: frozenset({"marvel.com"}),
        IdSources.METRON: frozenset({"metron.cloud"}),
        IdSources.MYANIMELIST: frozenset({"myanimelist.net"}),
        IdSources.PANELSYNDICATE: frozenset({"panelsyndicate.com"}),
        IdSources.UPC: frozenset({"barcodelookup.com", "go-upc.com"}),
    }
)

_ID_SOURCE_ALIAS_TO_SOURCE_MAP: MappingProxyType[str, IdSources] = MappingProxyType(
    {
        alias.value.lower()
        if isinstance(alias, IdSources)
        else alias.lower(): id_source
        for id_source, aliases in _ID_SOURCE_ALIASES.items()
        for alias in aliases | {id_source, ID_SOURCE_NAME_MAP[id_source]}
    }
)


def get_id_source_by_alias(
    id_source_alias: str, default: IdSources | None = DEFAULT_ID_SOURCE
) -> IdSources | None:
    """Get id source by alias."""
    return _ID_SOURCE_ALIAS_TO_SOURCE_MAP.get(id_source_alias.lower(), default)


def _build_source_alias_tree(node, source: IdSources, parts):
    if isinstance(node, IdSources):
        return
    part = parts[0]
    if len(parts) == 1:
        node[part] = source
    else:
        if part not in node:
            node[part] = {}
        _build_source_alias_tree(node[part], source, parts[1:])


def _create_source_alias_tree():
    tree = {}
    for source, aliases in _ID_SOURCE_ALIASES.items():
        for alias in aliases:
            parts = alias.split(".")
            if len(parts) <= 1:
                continue
            parts.reverse()
            _build_source_alias_tree(tree, source, parts)
    return tree


SOURCE_ALIAS_TREE = _create_source_alias_tree()
