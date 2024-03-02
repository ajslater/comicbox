"""Identifiers functions."""

import re
from logging import getLogger
from types import MappingProxyType

from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.schemas.identifier import NSS_KEY, URL_KEY

COMICVINE_NID = "comicvine"
METRON_NID = "metron"
COMIXOLOGY_NID = "comixology"
GCD_NID = "grandcomicsdatabase"
LCG_NID = "leagueofcomicgeeks"
ASIN_NID = "asin"
GTIN_NID = "gtin"
ISBN_NID = "isbn"
UPC_NID = "upc"
_CVDB_ALTERNATE_NID = "cvdb"
_CMXDB_ALTERNTATE_NID = "cmxdb"

LOG = getLogger(__name__)

# Metron uses the slug for an id, not the actual metron id.
# Metron could use an id to
IDENTIFIER_URL_MAP = MappingProxyType(
    {
        COMICVINE_NID: "https://comicvine.gamespot.com/c/",
        METRON_NID: "https://metron.cloud/",
        GCD_NID: "https://comics.org/",
        LCG_NID: "https://leaugeofcomicgeeks.com/",
        ASIN_NID: "https://www.amazon.com/dp/",
        COMIXOLOGY_NID: "https://www.comixology.com/c/digital-comic/",
        ISBN_NID: "https://isbndb.com/book/",
        UPC_NID: "https://barcodelookup.com/",
    }
)
TRAILING_SLUG = frozenset({LCG_NID})
COMICVINE_NSS_EXP = r"(?P<identifier>\d+-\d+)"
_WEB_EXPS = MappingProxyType(
    {
        COMICVINE_NID: rf"comicvine\.gamespot\.com/\S+\/{COMICVINE_NSS_EXP}/?",
        METRON_NID: r"metron\.cloud/(?P<identifier>\S+\/\S+)/?",
        GCD_NID: r"comics\.org/(?P<identifier>\S+\/\S+)/?",
        LCG_NID: r"leagueofcomicgeeks.com/(?P<identifier>\S+\/\S+)(/.*)?",
        ASIN_NID: r"amazon\.com/dp/(?P<identifier>\S+)",
        COMIXOLOGY_NID: r"comixology\.com/.+/.+/(?P<identifier>\d+)",
        ISBN_NID: r"isbndb\.com/book/(?P<identifier>\d{13}|\d{10})",
        UPC_NID: r"barcodelookup\.com/(?P<identifier>\d{12})",
    }
)
WEB_REGEX_URLS = MappingProxyType(
    {nid: re.compile(exp, flags=re.IGNORECASE) for nid, exp in _WEB_EXPS.items()}
)
_NIDS = (
    _CVDB_ALTERNATE_NID,
    ASIN_NID,
    _CMXDB_ALTERNTATE_NID,
    UPC_NID,
    GTIN_NID,
    ISBN_NID,
    COMIXOLOGY_NID,
    LCG_NID,
    GCD_NID,
    METRON_NID,
    COMICVINE_NID,
)
IDENTIFIER_EXP = r"(?P<type>" + r"|".join(_NIDS) + r")?:?(?P<nss>[\w-]+)"
IDENTIFIER_URN_NIDS = MappingProxyType(
    {
        COMICVINE_NID: frozenset(
            {
                COMICVINE_NID,
                None,
                _CVDB_ALTERNATE_NID,
                "comicvine.gamespot.org",
                "comic vine",
            }
        ),
        METRON_NID: frozenset({METRON_NID, "metron.cloud"}),
        GCD_NID: frozenset({GCD_NID, "comics.org", "grand comics database"}),
        LCG_NID: frozenset(
            {LCG_NID, "leagueofcomicgeeks.com", "league of comic geeks"}
        ),
        ASIN_NID: frozenset({ASIN_NID, "amazon", "amazon.com", "www.amazon.com"}),
        COMIXOLOGY_NID: frozenset(
            {COMIXOLOGY_NID, "comixology.com", _CMXDB_ALTERNTATE_NID}
        ),
        GTIN_NID: frozenset({GTIN_NID}),
        ISBN_NID: frozenset({ISBN_NID}),
        UPC_NID: frozenset({UPC_NID}),
    }
)
IDENTIFIER_URN_NIDS_REVERSE_MAP = MappingProxyType(
    {name: nid for nid, names in IDENTIFIER_URN_NIDS.items() for name in names}
)

GTIN_NID_ORDER = (
    GTIN_NID,
    ISBN_NID,
    ASIN_NID,
    COMIXOLOGY_NID,
    COMICVINE_NID,
    METRON_NID,
    GCD_NID,
    LCG_NID,
    UPC_NID,
)
NIDS_UNPARSE_NO_RESOURCE = frozenset(
    {ASIN_NID, COMIXOLOGY_NID, GTIN_NID, ISBN_NID, UPC_NID}
)
PARSE_COMICVINE_RE = re.compile(COMICVINE_NSS_EXP)
# XXX I haven't identified which program adds these "extra" notes encodings.
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
    url = url_prefix + nss + "/"
    if nid in TRAILING_SLUG:
        url += "s"
    return url


def create_identifier(nid, nss, url=None):
    """Create identifier dict from parts."""
    nss = _prefix_comicvine_issue_nss(nid, nss)
    if not url:
        url = get_url_from_identifier(nid, nss)
    return {NSS_KEY: nss, URL_KEY: url}


def parse_urn_identifier(tag: str, warn=True) -> tuple[str | None, str | None]:
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
    """Parse identifiers from strings."""
    nid, nss = parse_urn_identifier(item)
    if not nss:
        nid, nss = _parse_identifier_str(item)
    if naked_nid and not nid:
        nid = naked_nid

    return nid, nss


def to_urn_string(nid_str: str, nss_str: str):
    """Compose an urn string."""
    nid = NSIdentifier(nid_str)
    nss = NSSString(nss_str)
    urn = URN8141(nid=nid, nss=nss)
    return str(urn)
