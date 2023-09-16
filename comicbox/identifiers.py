"""Identifiers functions."""
import re
from types import MappingProxyType

from urnparse import URN8141, InvalidURNFormatError

SERIES_SUFFIX = "-series"
COMICVINE_NID = "comicvine"
COMICVINE_SERIES_NID = COMICVINE_NID + SERIES_SUFFIX
COMIXOLOGY_NID = "comixology"
ASIN_NID = "asin"
GTIN_NID = "gtin"
ISBN_NID = "isbn"
_CVDB_ALTERNATE_NID = "cvdb"
_CMXDB_ALTERNTATE_NID = "cmxdb"

CV_COMIC_PREFIX = "4000-"
CV_SERIES_PREFIX = "4050-"
MATCH_URLS = MappingProxyType(
    {
        COMICVINE_NID: "https://comicvine.gamespot.com/c/" + CV_COMIC_PREFIX,
        ASIN_NID: "https://www.amazon.com/dp/",
        COMIXOLOGY_NID: "https://www.comixology.com/c/digital-comic/",
        ISBN_NID: "https://isbndb.com/book/",
        COMICVINE_SERIES_NID: "https://comicvine.gamespot.com/c/" + CV_SERIES_PREFIX,
    }
)
_WEB_EXPS = MappingProxyType(
    {
        COMICVINE_NID: (
            rf"comicvine\.gamespot\.com/.+/{CV_COMIC_PREFIX}(?P<identifier>\d+)"
        ),
        ASIN_NID: r"amazon\.com/dp/(?P<identifier>\w+)",
        COMIXOLOGY_NID: r"comixology\.com/.+/.+/(?P<identifier>\d+)",
        ISBN_NID: r"isbndb\.com/book/(?P<identifier>\d{13}|\d{10})",
        COMICVINE_SERIES_NID: (
            rf"comicvine\.gamespot\.com/.+/{CV_SERIES_PREFIX}(?P<identifier>\d+)"
        ),
    }
)
WEB_REGEX_URLS = MappingProxyType(
    {key: re.compile(exp, flags=re.IGNORECASE) for key, exp in _WEB_EXPS.items()}
)
_IDENTIFIER_TYPES = (
    _CVDB_ALTERNATE_NID,
    ASIN_NID,
    _CMXDB_ALTERNTATE_NID,
    GTIN_NID,
    ISBN_NID,
    COMICVINE_NID,
    COMIXOLOGY_NID,
    CV_COMIC_PREFIX,
    COMICVINE_SERIES_NID,
    CV_SERIES_PREFIX,
)
IDENTIFIER_EXP = r"(?P<type>" + r"|".join(_IDENTIFIER_TYPES) + r")?(?P<code>\S+)"
_PARSE_EXTRA_RE = re.compile(IDENTIFIER_EXP, flags=re.IGNORECASE)
IDENTIFIER_URN_NIDS = MappingProxyType(
    {
        COMICVINE_NID: frozenset(
            {None, _CVDB_ALTERNATE_NID, "comicvine.gamespot.org", CV_COMIC_PREFIX}
        ),
        ASIN_NID: frozenset({"amazon", "amazon.com", "www.amazon.com"}),
        COMIXOLOGY_NID: frozenset({"comixology.com", _CMXDB_ALTERNTATE_NID}),
        GTIN_NID: frozenset(),
        ISBN_NID: frozenset(),
        COMICVINE_SERIES_NID: frozenset({COMICVINE_SERIES_NID, CV_SERIES_PREFIX}),
    }
)
GTIN_NID_ORDER = (
    GTIN_NID,
    ISBN_NID,
    ASIN_NID,
    COMIXOLOGY_NID,
    COMICVINE_NID,
    COMICVINE_SERIES_NID,
)


def get_web_link(identifier_type, code):
    """Get a url by type and code."""
    if not code:
        return None
    url_prefix = MATCH_URLS.get(identifier_type)
    if not url_prefix:
        return None
    return url_prefix + code + "/"


def parse_identifier_str(full_identifier):
    """Parse an identifier string with optional prefix."""
    match = _PARSE_EXTRA_RE.search(full_identifier)
    if not match:
        return None, full_identifier
    identifier_type = match.group("type")
    code = match.group("code")
    return identifier_type, code


def parse_urn_identifier(tag):
    """Parse an identifier from a tag."""
    try:
        urn = URN8141.from_string(tag)
        identifier_type = str(urn.namespace_id)
        code = urn.specific_string.decoded
    except InvalidURNFormatError:
        identifier_type = None
        code = None
    return identifier_type, code


def coerce_urn_nid(identifier_type):
    """Coerce an identifier type into an known urn NID."""
    if not identifier_type:
        return identifier_type
    identifier_type = identifier_type.lower()
    for canonical_nid, alternate_nids in IDENTIFIER_URN_NIDS.items():
        if identifier_type in alternate_nids:
            identifier_type = canonical_nid
            break
    return identifier_type
