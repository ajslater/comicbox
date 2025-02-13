"""Identifiers functions."""

import re
from contextlib import suppress
from dataclasses import asdict, dataclass
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.schemas.identifier import NSS_KEY, URL_KEY

# Should be an enum?
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

SLUG_REXP = r"(?:/\S*)?"
COMICVINE_LONG_NSS_EXP = r"(?P<nsstype>\d{4})-(?P<nss>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_NSS_EXP)
DEFAULT_NSS_TYPE = "issue"


@dataclass
class IdentifierTypes:
    """URL slugs for identifier types."""

    issue: str = ""
    volume: str = ""
    series: str = ""
    imprint: str = ""
    publisher: str = ""
    story: str = ""

    _default_type: str = ""
    _map: frozenbidict[str, str] | None = None

    @property
    def map(self) -> frozenbidict:
        """Initialize reverse dict."""
        if not self._map:
            trimmed_dict = {key: value for key, value in asdict(self).items() if value}
            self._map = frozenbidict(trimmed_dict)
        return self._map

    @property
    def default_slug_type(self) -> str:
        """Return the first allocated slug type."""
        if not self._default_type:
            for key, value in self.map.items():
                if value:
                    self._default_type = key
                    break
        return self._default_type


@dataclass
class IdentifierParts:
    """Identifier url parser and unparser."""

    domain: str
    types: IdentifierTypes
    url_path_regex: str
    url_path_template: str

    def __post_init__(self):
        """Initialize url_regex & template prefix."""
        sld = ".".join(self.domain.split(".")[-2:])
        exp = rf".*{sld}/" + self.url_path_regex
        self._url_regex_exp = exp
        self.url_regex = re.compile(exp, flags=re.IGNORECASE)
        self.url_prefix = f"https://{self.domain}/"

    def get_type_by_code(self, nss_type_code: str, default=DEFAULT_NSS_TYPE):
        """Get identifier type by url fragment or code."""
        return self.types.map.inverse.get(nss_type_code, default)

    def parse_url(self, url) -> tuple[str, str]:
        """Parse URL with regex."""
        match = self.url_regex.match(url)
        if not match:
            return "", ""
        try:
            nss_type_slug = match.group("nsstype")
        except IndexError:
            nss_type_slug = ""
        nss_type = self.get_type_by_code(nss_type_slug, self.types.default_slug_type)
        nss = match.group("nss") or ""
        return nss_type, nss

    def unparse_url(self, nss_type: str, nss: str) -> str:
        """Create url from identifier parts."""
        if nss_type and nss:
            type_value = getattr(self.types, nss_type)
            path = self.url_path_template.format(nsstype=type_value, nss=nss)
        else:
            path = ""
        return self.url_prefix + path


IDENTIFIER_PARTS_MAP = MappingProxyType(
    {
        ANILIST_NID: IdentifierParts(
            domain="anilist.co",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<nsstype>manga)/(?P<nss>\d+){SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        ASIN_NID: IdentifierParts(
            domain="www.amazon.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"dp/(?P<nss>\S+)",
            url_path_template="dp/{nss}",
        ),
        COMICVINE_NID: IdentifierParts(
            domain="comicvine.gamespot.com",
            types=IdentifierTypes(issue="4000", series="4050", publisher="4010"),
            url_path_regex=r"(?P<slug>\S+)/" + COMICVINE_LONG_NSS_EXP,
            url_path_template="c/{nsstype}-{nss}/",
        ),
        COMIXOLOGY_NID: IdentifierParts(
            domain="www.comixology.com",
            types=IdentifierTypes(issue="digital-comic"),
            url_path_regex=r"c/(?P<nsstype>\S+)/(?P<nss>\d+)",
            url_path_template="c/{nsstype}/{nss}",
        ),
        GCD_NID: IdentifierParts(
            domain="comics.org",
            types=IdentifierTypes(
                issue="issue", series="series", publisher="indicia_publisher"
            ),
            url_path_regex=r"(?P<nsstype>\w+)/(?P<nss>\d+)/?",
            url_path_template="{nsstype}/{nss}/",
        ),
        ISBN_NID: IdentifierParts(
            domain="isbndb.com",
            types=IdentifierTypes(issue="book", series="series"),
            url_path_regex=r"(?P<nsstype>book)/(?P<nss>[\d-]+)",
            url_path_template="{nsstype}/{nss}",
        ),
        KITSU_NID: IdentifierParts(
            domain="kitsu.app",
            types=IdentifierTypes(series="manga"),
            url_path_regex=r"(?P<nsstype>manga)/(?P<nss>\S+)",
            url_path_template="{nsstype}/{nss}",
        ),
        LCG_NID: IdentifierParts(
            domain="leagueofcomicgeeks.com",
            types=IdentifierTypes(
                issue="comic", series="comics/series", publisher="comics"
            ),
            url_path_regex=rf"(?P<nsstype>)/(?P<nss>){SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        MANGADEX_NID: IdentifierParts(
            domain="mangadex.org",
            types=IdentifierTypes(series="title"),
            url_path_regex=rf"(?P<nsstype>title)/(?P<nss>\S+){SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        MANGAUPDATES_NID: IdentifierParts(
            domain="mangaupdates.com",
            types=IdentifierTypes(series="series"),
            url_path_regex=rf"(?P<nsstype>series)/(?P<nss>\S+){SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        MARVEL_NID: IdentifierParts(
            domain="marvel.com",
            types=IdentifierTypes(issue="issue", series="series"),
            url_path_regex=rf"comics/(?P<nsstype>\w+)/(?P<nss>\d+){SLUG_REXP}",
            url_path_template="comics/{nsstype}/{nss}/s",
        ),
        METRON_NID: IdentifierParts(
            # Metron uses the slug for an id in most urls, not the actual metron id.
            domain="metron.cloud",
            types=IdentifierTypes(
                issue="issue",
                series="series",
                publisher="publisher",
                imprint="imprint",
                story="story",
            ),
            url_path_regex=r"(?P<nsstype>issue)/(?P<nss>\S+)/?",
            url_path_template="{nsstype}/{nss}",
        ),
        MYANIMELIST_NID: IdentifierParts(
            domain="myanimelist.net",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<nsstype>manga)/(?P<nss>\d+){SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        UPC_NID: IdentifierParts(
            domain="barcodelookup.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"(?P<nss>[\d-]+)",
            url_path_template="{nss}",
        ),
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
DEFAULT_NID = COMICVINE_NID
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


def normalize_comicvine_nss(nss_type, nss):
    """I expect its quite common to list the full comicvine code in situations where only the id is necessary."""
    match = PARSE_COMICVINE_RE.match(nss)
    if not match:
        return nss_type, nss
    try:
        nss_type_code = match.group("nsstype")
    except IndexError:
        return nss_type, nss
    nss_type = IDENTIFIER_PARTS_MAP[COMICVINE_NID].get_type_by_code(
        nss_type_code, nss_type
    )
    with suppress(IndexError):
        nss = match.group("nss")
    return nss_type, nss


def create_identifier(nid, nss, url=None, nss_type="issue"):
    """Create identifier dict from parts."""
    identifier = {}
    if not nid:
        nid = DEFAULT_NID
    if nss:
        if nid == COMICVINE_NID:
            nss_type, nss = normalize_comicvine_nss(nss_type, nss)
        identifier[NSS_KEY] = nss
    if not url and nss and (id_parts := IDENTIFIER_PARTS_MAP.get(nid)):
        url = id_parts.unparse_url(nss_type, nss)
    if url:
        identifier[URL_KEY] = url
    return identifier
