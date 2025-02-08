"""Universal Resource Name support."""

# ruff: noqa: ERA001
import re
from logging import getLogger
from types import MappingProxyType

from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.identifiers import (
    ANILIST_NID,
    ASIN_NID,
    COMICVINE_NID,
    COMIXOLOGY_NID,
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
    PARSE_COMICVINE_RE,
    UPC_NID,
)

LOG = getLogger(__name__)

_CVDB_ALTERNATE_NID = "cvdb"
_CMXDB_ALTERNATE_NID = "cmxdb"

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
IDENTIFIER_EXP = r"(?P<nid>" + r"|".join(_NIDS) + r")?:?(?P<nss>[\w-]+)"
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


# I haven't identified which program adds these "extra" notes encodings. Could be mylar.
_PARSE_EXTRA_RE = re.compile(IDENTIFIER_EXP, flags=re.IGNORECASE)


# def _prefix_comicvine_issue_nss(nid, nss):
#    """Add prefix to comicvine identifiers."""
#    if nid == COMICVINE_NID and not PARSE_COMICVINE_RE.search(nss):
#        return "4000-" + nss
#    return nss

# def _get_issue_url_from_identifier(nid, nss):
#    """Get URL from identifier."""
#    if not nss:
#        return None
#    url_prefix = IDENTIFIER_URL_MAP.get(nid, "")
#    url_prefix += IDENTIFIER_URL_PREFIX_ISSUE_MAP.get(nid, "")
#    if not url_prefix:
#        return None
#    slug = "/s" if nid in TRAILING_SLUG else ""
#    return url_prefix + nss + slug


def parse_urn_identifier(tag: str, warn: bool) -> tuple[str, str, str]:
    """Parse an identifier from a tag."""
    try:
        urn = URN8141.from_string(tag)
        nid = str(urn.namespace_id)
        if nid:
            nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), "")
        parts = urn.specific_string.parts
        nss_type = "issue"
        nss = str(parts[-1])
    except Exception:
        if warn:
            LOG.debug(f"Unable to decode urn: {tag}")
        nid = ""
        nss_type = ""
        nss = ""
    return nid, nss_type, nss


def _parse_identifier_str(full_identifier) -> tuple[str, str, str]:
    """Parse an identifier string with optional prefix."""
    if match := PARSE_COMICVINE_RE.search(full_identifier):
        nid = COMICVINE_NID
        try:
            nss_type = match.group("nss_type")
            nss = match.group("nss")
        except IndexError:
            pass
        else:
            return nid, nss_type, nss

    if match := _PARSE_EXTRA_RE.search(full_identifier):
        try:
            nid = match.group("nid")
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), "")
            nss_type = "issue"
            if nss := match.group("nss"):
                return nid, nss_type, nss
        except IndexError:
            pass

    return "", "", full_identifier


def parse_string_identifier(item: str, naked_nid=None) -> tuple[str, str, str]:
    """Parse identifiers from strings or xml dicts."""
    nid, nss_type, nss = parse_urn_identifier(item, warn=True)
    if not nss:
        nid, nss_type, nss = _parse_identifier_str(item)
    if naked_nid and not nid:
        nid = naked_nid
    if not nss_type:
        nss_type = "issue"

    return nid, nss_type, nss


def to_urn_string(nid_str: str, nss_str: str):
    """Compose an urn string."""
    if "." in nid_str:
        return ""
    nid = NSIdentifier(nid_str)
    nss = NSSString(nss_str)
    urn = URN8141(nid=nid, nss=nss)
    return str(urn)
