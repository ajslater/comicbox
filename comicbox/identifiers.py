"""Identifiers functions."""

import re
from logging import getLogger
from types import MappingProxyType

from bidict import frozenbidict
from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.schemas.identifier import NSS_KEY, URL_KEY

ANILIST_NID = "anilist"
ASIN_NID = "asin"
COMICVINE_NID = "comicvine"
_CVDB_ALTERNATE_NID = "cvdb"
COMIXOLOGY_NID = "comixology"
_CMXDB_ALTERNATE_NID = "cmxdb"
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

LOG = getLogger(__name__)

# Metron uses the slug for an id, not the actual metron id.
# Metron could use an id to
IDENTIFIER_URL_MAP = MappingProxyType(
    {
        ANILIST_NID: "https://anilist.co/manga/",
        ASIN_NID: "https://www.amazon.com/dp/",
        COMICVINE_NID: "https://comicvine.gamespot.com/c/",
        COMIXOLOGY_NID: "https://www.comixology.com/c/digital-comic/",
        GCD_NID: "https://comics.org/",
        KITSU_NID: "https://kitsu.app/manga/",
        ISBN_NID: "https://isbndb.com/book/",
        LCG_NID: "https://leaugeofcomicgeeks.com/",
        MANGADEX_NID: "https://mangadex.org/title/",
        MANGAUPDATES_NID: "https://mangaupdates.com/series/",
        MARVEL_NID: "https//marvel.com/comics/issue/",
        METRON_NID: "https://metron.cloud/issue/",
        MYANIMELIST_NID: "https://myanimelist.net/manga/",
        UPC_NID: "https://barcodelookup.com/",
    }
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

COMICVINE_NSS_EXP = r"(?P<identifier>\d+-\d+)"
SLUG_REXP = r"(?:/.*)?"
_WEB_EXPS = MappingProxyType(
    {
        ANILIST_NID: rf"anilist\.co/manga/(?P<identifier>\d+){SLUG_REXP}",
        ASIN_NID: r"amazon\.com/dp/(?P<identifier>\S+)",
        COMICVINE_NID: rf"comicvine\.gamespot\.com/\S+\/{COMICVINE_NSS_EXP}/?",
        COMIXOLOGY_NID: r"comixology\.com/.+/.+/(?P<identifier>\d+)",
        GCD_NID: r"comics\.org/(?P<identifier>\S+\/\S+)/?",
        ISBN_NID: r"isbndb\.com/book/(?P<identifier>\d{13}|\d{10})",
        KITSU_NID: r"kitsu.app/manga/(?P<identifier>\S+)",
        LCG_NID: rf"leagueofcomicgeeks.com/(?P<identifier>\S+\/\S+){SLUG_REXP}",
        MANGADEX_NID: rf"mangadex\.org/title/(?P<identifier>\S+){SLUG_REXP}",
        MANGAUPDATES_NID: rf"mangaupdates\.com/series/(?P<identifier>\S+){SLUG_REXP}",
        MARVEL_NID: rf"marvel\.com/issue/(?P<identifier>\d+){SLUG_REXP}",
        METRON_NID: r"metron\.cloud/(?P<identifier>\S+)/?",
        MYANIMELIST_NID: rf"myanimelist\.net/manga/(?P<identifier>\d+){SLUG_REXP}",
        UPC_NID: r"barcodelookup\.com/(?P<identifier>\d{12})",
    }
)
TRAILING_SLUG = frozenset(
    {ANILIST_NID, LCG_NID, MANGADEX_NID, MANGAUPDATES_NID, MARVEL_NID, MYANIMELIST_NID}
)
WEB_REGEX_URLS = MappingProxyType(
    {nid: re.compile(exp, flags=re.IGNORECASE) for nid, exp in _WEB_EXPS.items()}
)
_NIDS = (
    ANILIST_NID,
    ASIN_NID,
    COMICVINE_NID,
    _CVDB_ALTERNATE_NID,
    COMIXOLOGY_NID,
    _CMXDB_ALTERNATE_NID,
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
IDENTIFIER_EXP = r"(?P<type>" + r"|".join(_NIDS) + r")?:?(?P<nss>[\w-]+)"
IDENTIFIER_URN_NIDS = MappingProxyType(
    {
        ANILIST_NID: frozenset({ANILIST_NID, "anilist.co"}),
        ASIN_NID: frozenset({ASIN_NID, "amazon", "amazon.com", "www.amazon.com"}),
        COMICVINE_NID: frozenset(
            {
                COMICVINE_NID,
                None,
                _CVDB_ALTERNATE_NID,
                "comicvine.gamespot.org",
                "comic vine",
            }
        ),
        COMIXOLOGY_NID: frozenset(
            {COMIXOLOGY_NID, "comixology.com", _CMXDB_ALTERNATE_NID}
        ),
        GCD_NID: frozenset({GCD_NID, "comics.org", "grand comics database"}),
        GTIN_NID: frozenset({GTIN_NID}),
        ISBN_NID: frozenset({ISBN_NID}),
        KITSU_NID: frozenset({KITSU_NID, "kistu.app"}),
        LCG_NID: frozenset(
            {LCG_NID, "leagueofcomicgeeks.com", "league of comic geeks"}
        ),
        MANGADEX_NID: frozenset({MANGADEX_NID, "mangadex.org"}),
        MANGAUPDATES_NID: frozenset({MANGAUPDATES_NID, "mangaupdates.com"}),
        MARVEL_NID: frozenset({MARVEL_NID, "marvel.com"}),
        METRON_NID: frozenset({METRON_NID, "metron.cloud"}),
        MYANIMELIST_NID: frozenset({MYANIMELIST_NID, "myanimelist.net"}),
        UPC_NID: frozenset({UPC_NID}),
    }
)
IDENTIFIER_URN_NIDS_REVERSE_MAP = MappingProxyType(
    {name: nid for nid, names in IDENTIFIER_URN_NIDS.items() for name in names}
)


NIDS_UNPARSE_NO_RESOURCE = frozenset(
    {ASIN_NID, COMIXOLOGY_NID, GTIN_NID, ISBN_NID, UPC_NID}
)
PARSE_COMICVINE_RE = re.compile(COMICVINE_NSS_EXP)
# I haven't identified which program adds these "extra" notes encodings. Could be mylar.
_PARSE_EXTRA_RE = re.compile(IDENTIFIER_EXP, flags=re.IGNORECASE)


def _prefix_comicvine_issue_nss(nid, nss):
    """Add prefix to comicvine identifiers."""
    if nid == COMICVINE_NID and not PARSE_COMICVINE_RE.search(nss):
        return "4000-" + nss
    return nss


def get_url_from_identifier(nid, nss):
    """Get URL from identifier."""
    if not nss:
        return None
    url_prefix = IDENTIFIER_URL_MAP.get(nid)
    if not url_prefix:
        return None
    slug = "s" if nid in TRAILING_SLUG else ""
    return url_prefix + nss + "/" + slug


def create_identifier(nid, nss, url=None):
    """Create identifier dict from parts."""
    nss = _prefix_comicvine_issue_nss(nid, nss)
    if not url:
        url = get_url_from_identifier(nid, nss)
    if nss and url:
        return {NSS_KEY: nss, URL_KEY: url}
    return {}


def parse_urn_identifier(tag: str, warn: bool = True) -> tuple[str | None, str | None]:  # noqa: FBT002
    """Parse an identifier from a tag."""
    try:
        urn = URN8141.from_string(tag)
        nid = str(urn.namespace_id)
        if nid:
            nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower())
        parts = urn.specific_string.parts
        nss = str(parts[-1])
    except Exception:
        if warn:
            LOG.debug(f"Unable to decode urn: {tag}")
        nid = None
        nss = None
    return nid, nss


def _parse_identifier_str(full_identifier):
    """Parse an identifier string with optional prefix."""
    if match := PARSE_COMICVINE_RE.search(full_identifier):
        nid = COMICVINE_NID
        if nss := match.group("identifier"):
            return nid, nss

    if match := _PARSE_EXTRA_RE.search(full_identifier):
        nid = match.group("type")
        if nid:
            nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower())
        if nss := match.group("nss"):
            return nid, nss

    return None, full_identifier


def parse_identifier(item, naked_nid=None):
    """Parse identifiers from strings or xml dicts."""
    nid, nss = parse_urn_identifier(item, warn=True)
    if not nss:
        nid, nss = _parse_identifier_str(item)
    if naked_nid and not nid:
        nid = naked_nid

    return nid, nss


def to_urn_string(nid_str: str, nss_str: str):
    """Compose an urn string."""
    if "." in nid_str:
        return ""
    nid = NSIdentifier(nid_str)
    nss = NSSString(nss_str)
    urn = URN8141(nid=nid, nss=nss)
    return str(urn)
