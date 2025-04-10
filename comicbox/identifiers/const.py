"""Identifier consts."""

import re
from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

NSS_KEY = "nss"
URL_KEY = "url"


class NIDs(Enum):
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


NID_VALUES = (nid.value for nid in NIDs)


# Non standard
class AlternateNIDs(Enum):
    """Alternate NID Names."""

    # TODO not really NIDs, but aliases, move into ALIASES MAP
    CVDB_ALTERNATE = "cvdb"
    CMXDB_ALTERNATE = "cmxdb"


DEFAULT_NID = NIDs.COMICVINE.value
DEFAULT_NSS_TYPE = "issue"


# TODO rename to names
NID_ORIGIN_MAP = frozenbidict(
    {
        # DBs
        NIDs.ANILIST.value: "AniList",
        NIDs.COMICVINE.value: "Comic Vine",
        NIDs.COMIXOLOGY.value: "ComiXology",
        NIDs.GCD.value: "Grand Comics Database",
        NIDs.KITSU.value: "Kitsu",
        NIDs.LCG.value: "League of Comic Geeks",
        NIDs.MANGADEX.value: "MangaDex",
        NIDs.MANGAUPDATES.value: "MangaUpdates",
        NIDs.MARVEL.value: "Marvel",
        NIDs.METRON.value: "Metron",
        NIDs.MYANIMELIST.value: "MyAnimeList",
        # GITNs
        NIDs.ASIN.value: "Amazon",
        NIDs.GTIN.value: "GTIN",
        NIDs.ISBN.value: "ISBN",
        NIDs.UPC.value: "UPC",
    }
)
# TODO combine with NID_ORIGIN_MAP look at uses
_IDENTIFIER_URN_NID_ALIASES = MappingProxyType(
    {
        NIDs.ANILIST.value: frozenset({"anilist.co"}),
        NIDs.ASIN.value: frozenset({"amazon.com", "www.amazon.com"}),
        NIDs.COMICVINE.value: frozenset(
            {AlternateNIDs.CVDB_ALTERNATE.value, "comicvine.gamespot.org"}
        ),
        NIDs.COMIXOLOGY.value: frozenset(
            {"comixology.com", AlternateNIDs.CMXDB_ALTERNATE.value}
        ),
        NIDs.GCD.value: frozenset({"comics.org"}),
        NIDs.GTIN.value: frozenset({}),
        NIDs.ISBN.value: frozenset({}),
        NIDs.KITSU.value: frozenset({"kistu.app"}),
        NIDs.LCG.value: frozenset({"leagueofcomicgeeks.com"}),
        NIDs.MANGADEX.value: frozenset({"mangadex.org"}),
        NIDs.MANGAUPDATES.value: frozenset({"mangaupdates.com"}),
        NIDs.MARVEL.value: frozenset({"marvel.com"}),
        NIDs.METRON.value: frozenset({"metron.cloud"}),
        NIDs.MYANIMELIST.value: frozenset({"myanimelist.net"}),
        NIDs.UPC.value: frozenset({}),
    }
)

COMICVINE_LONG_NSS_EXP = r"(?P<nsstype>\d{4})-(?P<nss>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_NSS_EXP)
_ALL_NIDS = (*NID_VALUES, *(nid.value for nid in AlternateNIDs))
IDENTIFIER_RE_EXP = r"(?P<nid>" + r"|".join(_ALL_NIDS) + r"):?(?P<nss>[\w-]+)"


def _create_identifier_urn_ids_maps():
    identifier_urn_ids_reverse = {}
    for nid, aliases in _IDENTIFIER_URN_NID_ALIASES.items():
        all_aliases = aliases | {nid, NID_ORIGIN_MAP[nid].lower()}
        for alias in all_aliases:
            identifier_urn_ids_reverse[alias] = nid
    return identifier_urn_ids_reverse


# TODO rename not urns
IDENTIFIER_URN_NIDS_REVERSE_MAP = _create_identifier_urn_ids_maps()
