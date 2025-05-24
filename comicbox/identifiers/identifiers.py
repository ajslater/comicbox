"""Identifiers functions."""

import re
from contextlib import suppress
from dataclasses import asdict, dataclass
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.identifiers import (
    COMICVINE_LONG_ID_KEY_EXP,
    DEFAULT_ID_SOURCE,
    DEFAULT_ID_TYPE,
    ID_KEY_KEY,
    PARSE_COMICVINE_RE,
    URL_KEY,
    IdSources,
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

    def get_type_by_code(self, id_type_code: str, default=DEFAULT_ID_TYPE):
        """Get identifier type by url fragment or code."""
        return self.types.map.inverse.get(id_type_code, default)

    def parse_url(self, url) -> tuple[str, str]:
        """Parse URL with regex."""
        match = self.url_regex.match(url)
        if not match:
            return "", ""
        try:
            id_type_slug = match.group("id_keytype")
        except IndexError:
            id_type_slug = ""
        id_type = self.get_type_by_code(id_type_slug, self.types.default_slug_type)
        id_key = match.group("id_key") or ""
        return id_type, id_key

    def unparse_url(self, id_type: str, id_key: str) -> str:
        """Create url from identifier parts."""
        if id_type and id_key:
            type_value = getattr(self.types, id_type)
            path = self.url_path_template.format(id_keytype=type_value, id_key=id_key)
        else:
            path = ""
        return self.url_prefix + path


IDENTIFIER_PARTS_MAP = MappingProxyType(
    {
        IdSources.ANILIST.value: IdentifierParts(
            domain="anilist.co",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<id_keytype>manga)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="{id_keytype}/{id_key}/s",
        ),
        IdSources.ASIN.value: IdentifierParts(
            domain="www.amazon.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"dp/(?P<id_key>\S+)",
            url_path_template="dp/{id_key}",
        ),
        IdSources.COMICVINE.value: IdentifierParts(
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
            url_path_regex=r"(?P<slug>\S+)/" + COMICVINE_LONG_ID_KEY_EXP,
            url_path_template="c/{id_keytype}-{id_key}/",
        ),
        IdSources.COMIXOLOGY.value: IdentifierParts(
            domain="www.comixology.com",
            types=IdentifierTypes(issue="digital-comic"),
            url_path_regex=r"c/(?P<id_keytype>\S+)/(?P<id_key>\d+)",
            url_path_template="c/{id_keytype}/{id_key}",
        ),
        IdSources.GCD.value: IdentifierParts(
            domain="comics.org",
            types=IdentifierTypes(
                character="character",
                creator="creator",
                issue="issue",
                series="series",
                publisher="indicia_publisher",
                universe="universe",
            ),
            url_path_regex=r"(?P<id_keytype>\S+)/(?P<id_key>\d+)/?",
            url_path_template="{id_keytype}/{id_key}/",
        ),
        IdSources.ISBN.value: IdentifierParts(
            domain="isbndb.com",
            types=IdentifierTypes(issue="book", series="series"),
            url_path_regex=r"(?P<id_keytype>book)/(?P<id_key>[\d-]+)",
            url_path_template="{id_keytype}/{id_key}",
        ),
        IdSources.KITSU.value: IdentifierParts(
            domain="kitsu.app",
            types=IdentifierTypes(series="manga"),
            url_path_regex=r"(?P<id_keytype>manga)/(?P<id_key>\S+)",
            url_path_template="{id_keytype}/{id_key}",
        ),
        IdSources.LCG.value: IdentifierParts(
            domain="leagueofcomicgeeks.com",
            types=IdentifierTypes(
                issue="comic", series="comics/series", publisher="comics"
            ),
            url_path_regex=rf"(?P<id_keytype>\S+)/(?P<id_key>\S+){_SLUG_REXP}",
            url_path_template="{id_keytype}/{id_key}/s",
        ),
        IdSources.MANGADEX.value: IdentifierParts(
            domain="mangadex.org",
            types=IdentifierTypes(series="title"),
            url_path_regex=rf"(?P<id_keytype>title)/(?P<id_key>\S+){_SLUG_REXP}",
            url_path_template="{id_keytype}/{id_key}/s",
        ),
        IdSources.MANGAUPDATES.value: IdentifierParts(
            domain="mangaupdates.com",
            types=IdentifierTypes(series="series"),
            url_path_regex=rf"(?P<id_keytype>series)/(?P<id_key>\S+){_SLUG_REXP}",
            url_path_template="{id_keytype}/{id_key}/s",
        ),
        IdSources.MARVEL.value: IdentifierParts(
            domain="marvel.com",
            types=IdentifierTypes(issue="issue", series="series"),
            url_path_regex=rf"comics/(?P<id_keytype>issue|series)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="comics/{id_keytype}/{id_key}/s",
        ),
        IdSources.METRON.value: IdentifierParts(
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
            url_path_regex=r"(?P<id_keytype>\S+)/(?P<id_key>\S+)/?",
            url_path_template="{id_keytype}/{id_key}",
        ),
        IdSources.MYANIMELIST.value: IdentifierParts(
            domain="myanimelist.net",
            types=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<id_keytype>manga)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="{id_keytype}/{id_key}/s",
        ),
        IdSources.UPC.value: IdentifierParts(
            domain="barcodelookup.com",
            types=IdentifierTypes(issue="issue"),
            url_path_regex=r"(?P<id_key>[\d-]+)",
            url_path_template="{id_key}",
        ),
    }
)


def _normalize_comicvine_id_key(id_type, id_key):
    """I expect its quite common to list the full comicvine code in situations where only the id is necessary."""
    match = PARSE_COMICVINE_RE.match(id_key)
    if not match:
        return id_type, id_key
    try:
        id_type_code = match.group("id_keytype")
    except IndexError:
        return id_type, id_key
    id_type = IDENTIFIER_PARTS_MAP[IdSources.COMICVINE.value].get_type_by_code(
        id_type_code, id_type
    )
    with suppress(IndexError):
        id_key = match.group("id_key")
    return id_type, id_key


def create_identifier(
    id_source,
    id_key,
    url="",
    id_type=DEFAULT_ID_TYPE,
    default_id_source=DEFAULT_ID_SOURCE,
):
    """Create identifier dict from parts."""
    identifier = {}
    if not id_source:
        id_source = default_id_source
    if id_key:
        if id_source == IdSources.COMICVINE.value:
            id_type, id_key = _normalize_comicvine_id_key(id_type, id_key)
        if id_key:
            identifier[ID_KEY_KEY] = id_key
    if not url and id_key and (id_parts := IDENTIFIER_PARTS_MAP.get(id_source)):
        url = id_parts.unparse_url(id_type, id_key)
    if url:
        identifier[URL_KEY] = url
    return identifier
