"""Identifiers functions."""

import re
from contextlib import suppress
from dataclasses import asdict, dataclass
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.identifiers.const import (
    COMICVINE_LONG_NSS_EXP,
    DEFAULT_NID,
    DEFAULT_NSS_TYPE,
    NSS_KEY,
    PARSE_COMICVINE_RE,
    URL_KEY,
    NIDs,
)

_SLUG_REXP = r"(?:/\S*)?"


@dataclass
class IdentifierTypes:
    """URL slugs for identifier types."""

    arc: str = ""
    character: str = ""
    genre: str = ""
    imprint: str = ""
    issue: str = ""
    location: str = ""
    publisher: str = ""
    reprint: str = ""
    series: str = ""
    story: str = ""
    tag: str = ""
    team: str = ""
    universe: str = ""
    volume: str = ""
    role: str = ""
    creator: str = ""

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
        self._url_regex_exp = exp  # pyright: ignore[reportUninitializedInstanceVariable]
        self.url_regex = re.compile(exp, flags=re.IGNORECASE)  # pyright: ignore[reportUninitializedInstanceVariable]
        self.url_prefix = f"https://{self.domain}/"  # pyright: ignore[reportUninitializedInstanceVariable]

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
        NIDs.ANILIST.value: IdentifierParts(
            domain="anilist.co",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<nsstype>manga)/(?P<nss>\d+){_SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        NIDs.ASIN.value: IdentifierParts(
            domain="www.amazon.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"dp/(?P<nss>\S+)",
            url_path_template="dp/{nss}",
        ),
        NIDs.COMICVINE.value: IdentifierParts(
            domain="comicvine.gamespot.com",
            types=IdentifierTypes(
                arc="4045",
                character="4005",
                creator="4040",
                issue="4000",
                location="4020",
                publisher="4010",
                series="4050",
                team="4060",
            ),
            url_path_regex=r"(?P<slug>\S+)/" + COMICVINE_LONG_NSS_EXP,
            url_path_template="c/{nsstype}-{nss}/",
        ),
        NIDs.COMIXOLOGY.value: IdentifierParts(
            domain="www.comixology.com",
            types=IdentifierTypes(issue="digital-comic"),
            url_path_regex=r"c/(?P<nsstype>\S+)/(?P<nss>\d+)",
            url_path_template="c/{nsstype}/{nss}",
        ),
        NIDs.GCD.value: IdentifierParts(
            domain="comics.org",
            types=IdentifierTypes(
                character="character",
                creator="creator",
                issue="issue",
                series="series",
                publisher="indicia_publisher",
                universe="universe",
            ),
            url_path_regex=r"(?P<nsstype>\S+)/(?P<nss>\d+)/?",
            url_path_template="{nsstype}/{nss}/",
        ),
        NIDs.ISBN.value: IdentifierParts(
            domain="isbndb.com",
            types=IdentifierTypes(issue="book", series="series"),
            url_path_regex=r"(?P<nsstype>book)/(?P<nss>[\d-]+)",
            url_path_template="{nsstype}/{nss}",
        ),
        NIDs.KITSU.value: IdentifierParts(
            domain="kitsu.app",
            types=IdentifierTypes(series="manga"),
            url_path_regex=r"(?P<nsstype>manga)/(?P<nss>\S+)",
            url_path_template="{nsstype}/{nss}",
        ),
        NIDs.LCG.value: IdentifierParts(
            domain="leagueofcomicgeeks.com",
            types=IdentifierTypes(
                issue="comic", series="comics/series", publisher="comics"
            ),
            url_path_regex=rf"(?P<nsstype>\S+)/(?P<nss>\S+){_SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        NIDs.MANGADEX.value: IdentifierParts(
            domain="mangadex.org",
            types=IdentifierTypes(series="title"),
            url_path_regex=rf"(?P<nsstype>title)/(?P<nss>\S+){_SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        NIDs.MANGAUPDATES.value: IdentifierParts(
            domain="mangaupdates.com",
            types=IdentifierTypes(series="series"),
            url_path_regex=rf"(?P<nsstype>series)/(?P<nss>\S+){_SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        NIDs.MARVEL.value: IdentifierParts(
            domain="marvel.com",
            types=IdentifierTypes(issue="issue", series="series"),
            url_path_regex=rf"comics/(?P<nsstype>issue|series)/(?P<nss>\d+){_SLUG_REXP}",
            url_path_template="comics/{nsstype}/{nss}/s",
        ),
        NIDs.METRON.value: IdentifierParts(
            # Metron uses the slug for an id in most urls
            #   but can also use the numeric metron id which redirects to the slug
            # https://github.com/Metron-Project/metron/blob/master/metron/urls.py
            domain="metron.cloud",
            types=IdentifierTypes(
                arc="arc",
                character="character",
                creator="creator",
                genre="genre",  # Not Yet Implemented on API
                imprint="imprint",
                issue="issue",
                location="location",  # Not Yet Implemented on API
                publisher="publisher",
                reprint="reprint",  # Not Yet Implemented on API
                role="role",
                series="series",
                story="story",  # Not Yet Implemented on API
                tag="tag",
                team="team",
                universe="universe",
            ),
            url_path_regex=r"(?P<nsstype>\S+)/(?P<nss>\S+)/?",
            url_path_template="{nsstype}/{nss}",
        ),
        NIDs.MYANIMELIST.value: IdentifierParts(
            domain="myanimelist.net",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<nsstype>manga)/(?P<nss>\d+){_SLUG_REXP}",
            url_path_template="{nsstype}/{nss}/s",
        ),
        NIDs.UPC.value: IdentifierParts(
            domain="barcodelookup.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"(?P<nss>[\d-]+)",
            url_path_template="{nss}",
        ),
    }
)


def _normalize_comicvine_nss(nss_type, nss):
    """I expect its quite common to list the full comicvine code in situations where only the id is necessary."""
    match = PARSE_COMICVINE_RE.match(nss)
    if not match:
        return nss_type, nss
    try:
        nss_type_code = match.group("nsstype")
    except IndexError:
        return nss_type, nss
    nss_type = IDENTIFIER_PARTS_MAP[NIDs.COMICVINE.value].get_type_by_code(
        nss_type_code, nss_type
    )
    with suppress(IndexError):
        nss = match.group("nss")
    return nss_type, nss


def create_identifier(
    nid, nss, url="", nss_type=DEFAULT_NSS_TYPE, default_nid=DEFAULT_NID
):
    """Create identifier dict from parts."""
    identifier = {}
    if not nid:
        nid = default_nid
    if nss:
        if nid == NIDs.COMICVINE.value:
            nss_type, nss = _normalize_comicvine_nss(nss_type, nss)
        if nss:
            identifier[NSS_KEY] = nss
    if not url and nss and (id_parts := IDENTIFIER_PARTS_MAP.get(nid)):
        url = id_parts.unparse_url(nss_type, nss)
    if url:
        identifier[URL_KEY] = url
    return identifier
