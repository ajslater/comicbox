"""Identifier consts."""

import re
from types import MappingProxyType

from bidict import frozenbidict

# TODO make an enum
ANILIST_NID = "anilist"
ASIN_NID = "asin"
COMICVINE_NID = "comicvine"
COMIXOLOGY_NID = "comixology"
GCD_NID = "grandcomicsdatabase"
GTIN_NID = "gtin"
ISBN_NID = "isbn"
KITSU_NID = "kitsu"
LCG_NID = "leagueofcomicgeeks"
MANGADEX_NID = "mangadex"
MANGAUPDATES_NID = "mangaupdates"
MARVEL_NID = "marvel"
METRON_NID = "metron"
MYANIMELIST_NID = "myanimelist"
UPC_NID = "upc"
NSS_KEY = "nss"
URL_KEY = "url"
# Non standard
CVDB_ALTERNATE_NID = "cvdb"
CMXDB_ALTERNATE_NID = "cmxdb"

NID_ORDER = (
    # Comic DBs
    METRON_NID,
    COMICVINE_NID,
    GCD_NID,
    LCG_NID,
    MARVEL_NID,
    # Manga DBs
    ANILIST_NID,
    KITSU_NID,
    MANGADEX_NID,
    MANGAUPDATES_NID,
    MYANIMELIST_NID,
    # GTINs
    GTIN_NID,
    ISBN_NID,
    UPC_NID,
    ASIN_NID,
    COMIXOLOGY_NID,
)


NID_ORIGIN_MAP = frozenbidict(
    {
        # DBs
        ANILIST_NID: "AniList",
        COMICVINE_NID: "Comic Vine",
        COMIXOLOGY_NID: "ComiXology",
        GCD_NID: "Grand Comics Database",
        KITSU_NID: "Kitsu",
        LCG_NID: "League of Comic Geeks",
        MANGADEX_NID: "MangaDex",
        MANGAUPDATES_NID: "MangaUpdates",
        MARVEL_NID: "Marvel",
        METRON_NID: "Metron",
        MYANIMELIST_NID: "MyAnimeList",
        # GITNs
        ASIN_NID: "Amazon",
        GTIN_NID: "GTIN",
        ISBN_NID: "ISBN",
        UPC_NID: "UPC",
    }
)
DEFAULT_NID = COMICVINE_NID
DEFAULT_NSS_TYPE = "issue"

COMICVINE_LONG_NSS_EXP = r"(?P<nsstype>\d{4})-(?P<nss>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_NSS_EXP)
_NIDS = (
    # TODO replace with const enum
    ANILIST_NID,
    ASIN_NID,
    COMICVINE_NID,
    CVDB_ALTERNATE_NID,
    COMIXOLOGY_NID,
    CMXDB_ALTERNATE_NID,
    GCD_NID,
    GTIN_NID,
    ISBN_NID,
    KITSU_NID,
    LCG_NID,
    MANGADEX_NID,
    MANGAUPDATES_NID,
    MARVEL_NID,
    METRON_NID,
    MYANIMELIST_NID,
    UPC_NID,
)
IDENTIFIER_RE_EXP = r"(?P<nid>" + r"|".join(_NIDS) + r"):?(?P<nss>[\w-]+)"

_IDENTIFIER_URN_NID_ALIASES = MappingProxyType(
    {
        ANILIST_NID: frozenset({"anilist.co"}),
        ASIN_NID: frozenset({"amazon.com", "www.amazon.com"}),
        COMICVINE_NID: frozenset({CVDB_ALTERNATE_NID, "comicvine.gamespot.org"}),
        COMIXOLOGY_NID: frozenset({"comixology.com", CMXDB_ALTERNATE_NID}),
        GCD_NID: frozenset({"comics.org"}),
        GTIN_NID: frozenset({}),
        ISBN_NID: frozenset({}),
        KITSU_NID: frozenset({"kistu.app"}),
        LCG_NID: frozenset({"leagueofcomicgeeks.com"}),
        MANGADEX_NID: frozenset({"mangadex.org"}),
        MANGAUPDATES_NID: frozenset({"mangaupdates.com"}),
        MARVEL_NID: frozenset({"marvel.com"}),
        METRON_NID: frozenset({"metron.cloud"}),
        MYANIMELIST_NID: frozenset({"myanimelist.net"}),
        UPC_NID: frozenset({}),
    }
)


def _create_identifier_urn_ids_maps():
    identifier_urn_ids_reverse = {}
    for nid, aliases in _IDENTIFIER_URN_NID_ALIASES.items():
        all_aliases = aliases | {nid, NID_ORIGIN_MAP[nid].lower()}
        for alias in all_aliases:
            identifier_urn_ids_reverse[alias] = nid
    return identifier_urn_ids_reverse


# TODO rename not urns
IDENTIFIER_URN_NIDS_REVERSE_MAP = _create_identifier_urn_ids_maps()

