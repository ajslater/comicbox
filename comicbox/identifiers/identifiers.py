"""Identifiers functions."""

import re
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlparse

from bidict import frozenbidict

from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import SOURCE_ALIAS_TREE, get_id_source_by_alias
from comicbox.identifiers import (
    COMICVINE_LONG_ID_KEY_EXP,
    DEFAULT_ID_SOURCE,
    DEFAULT_ID_TYPE,
    ID_KEY_KEY,
    ID_TYPE_KEY,
    ID_TYPE_NAMES,
    PARSE_COMICVINE_RE,
)

_ID_TYPES = frozenset(ID_TYPE_NAMES)

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
            # Only the slug fields. The memo fields are also fields, so
            # walking every one of them put _default_type's value in the
            # map, colliding with the type it was remembering.
            trimmed_dict = {
                name: value
                for name in ID_TYPE_NAMES
                if (value := getattr(self, name, ""))
            }
            self._map = frozenbidict(trimmed_dict)
        return self._map

    @property
    def default_slug_type(self) -> str:
        """Return the type to assume when a url names one we don't know."""
        if not self._default_type:
            # A comic's own page is the issue's, so that's the type an
            # unrecognized one most likely is. Falling back to whichever
            # type happened to be declared first made them all arcs.
            if self.issue:
                self._default_type = DEFAULT_ID_TYPE
            else:
                for key, value in self.map.items():
                    if value:
                        self._default_type = key
                        break
        return self._default_type


@dataclass
class IdentifierParts:
    """Identifier url parser and unparser."""

    domain: str
    id_type: IdentifierTypes
    url_path_regex: str
    url_path_template: str
    https: bool = True

    def __post_init__(self) -> None:
        """Initialize url_regex & template prefix."""
        scheme = "https" if self.https else "http"
        self.url_prefix = f"{scheme}://{self.domain}/"  # pyright: ignore[reportUninitializedInstanceVariable]
        self.url_path_regex_compiled = re.compile(self.url_path_regex, re.IGNORECASE)  # pyright: ignore[reportUninitializedInstanceVariable]

    def get_type_by_code(
        self, id_type_code: str, default: str = DEFAULT_ID_TYPE
    ) -> str:
        """Get identifier type by url fragment or code."""
        return self.id_type.map.inverse.get(id_type_code, default)

    def parse_url_path(self, url: str) -> tuple[str, str]:
        """Parse URL path with regex, or return no match."""
        obj = urlparse(url)
        match = self.url_path_regex_compiled.search(obj.path[1:])
        if not match:
            # A known database's own site is full of pages that are not an
            # id: /about, /search, the front page. Handing the raw path back
            # as the key minted ids like "/about/" that nothing can look up.
            return "", ""
        try:
            id_type_slug = match.group("id_type")
        except IndexError:
            id_type_slug = ""
        id_type = self.get_type_by_code(id_type_slug, self.id_type.default_slug_type)
        id_key = match.group("id_key") or ""
        return id_type, id_key

    def unparse_url(self, id_type: str, id_key: str) -> str:
        """Create url from identifier parts."""
        url = ""
        if ":" in id_key:
            # A prefix normalize_key didn't recognize; no source uses colons
            # in its path segments, so emit no url rather than a broken one.
            return url
        # A type is looked up in the slug map, never fetched off the
        # dataclass: id_type is unvalidated, and an "id_type: map" put the
        # repr of the map itself in the url.
        if type_value := self.id_type.map.get(id_type):
            path = self.url_path_template.format(id_type=type_value, id_key=id_key)
            url = self.url_prefix + path
        return url


IDENTIFIER_PARTS_MAP: MappingProxyType[IdSources, IdentifierParts] = MappingProxyType(
    {
        IdSources.ANILIST: IdentifierParts(
            domain="anilist.co",
            id_type=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<id_type>manga)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="{id_type}/{id_key}/s",
        ),
        IdSources.ASIN: IdentifierParts(
            domain="www.amazon.com",
            id_type=IdentifierTypes(issue="issue"),
            # An asin is one path segment. \S+ swallowed the /ref=... amazon
            # appends to nearly every url into the id.
            url_path_regex=r"dp/(?P<id_key>[^/]+)",
            url_path_template="dp/{id_key}",
        ),
        IdSources.COMICVINE: IdentifierParts(
            domain="comicvine.gamespot.com",
            id_type=IdentifierTypes(
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
            url_path_template="c/{id_type}-{id_key}/",
        ),
        IdSources.COMIXOLOGY: IdentifierParts(
            domain="www.comixology.com",
            id_type=IdentifierTypes(issue="digital-comic"),
            url_path_regex=r"c/(?P<id_type>\S+)/(?P<id_key>\d+)",
            url_path_template="c/{id_type}/{id_key}",
        ),
        IdSources.GCD: IdentifierParts(
            domain="comics.org",
            id_type=IdentifierTypes(
                character="character",
                creator="creator",
                issue="issue",
                series="series",
                publisher="indicia_publisher",
                universe="universe",
            ),
            url_path_regex=r"(?P<id_type>\S+)/(?P<id_key>\d+)/?",
            url_path_template="{id_type}/{id_key}/",
        ),
        IdSources.ISBN: IdentifierParts(
            domain="isbndb.com",
            id_type=IdentifierTypes(issue="book", series="series"),
            # Both declared slugs, or a series url unparse_url built parsed
            # back as nothing.
            url_path_regex=r"(?P<id_type>book|series)/(?P<id_key>[\d-]+)",
            url_path_template="{id_type}/{id_key}",
        ),
        IdSources.KITSU: IdentifierParts(
            domain="kitsu.app",
            id_type=IdentifierTypes(series="manga"),
            url_path_regex=r"(?P<id_type>manga)/(?P<id_key>[^/]+)",
            url_path_template="{id_type}/{id_key}",
        ),
        IdSources.LCG: IdentifierParts(
            domain="leagueofcomicgeeks.com",
            id_type=IdentifierTypes(
                issue="comic", series="comics/series", publisher="comics"
            ),
            # The series slug is two segments, so the type is spelled out
            # longest first rather than matched generically. A greedy \S+ for
            # either group ate the whole path and read the trailing name slug
            # as the id.
            url_path_regex=rf"(?P<id_type>comics/series|comics|comic)/(?P<id_key>[^/]+){_SLUG_REXP}",
            url_path_template="{id_type}/{id_key}/s",
        ),
        IdSources.MANGADEX: IdentifierParts(
            domain="mangadex.org",
            id_type=IdentifierTypes(series="title"),
            url_path_regex=rf"(?P<id_type>title)/(?P<id_key>[^/]+){_SLUG_REXP}",
            url_path_template="{id_type}/{id_key}/s",
        ),
        IdSources.MANGAUPDATES: IdentifierParts(
            domain="mangaupdates.com",
            id_type=IdentifierTypes(series="series"),
            url_path_regex=rf"(?P<id_type>series)/(?P<id_key>[^/]+){_SLUG_REXP}",
            url_path_template="{id_type}/{id_key}/s",
        ),
        IdSources.MARVEL: IdentifierParts(
            domain="marvel.com",
            id_type=IdentifierTypes(issue="issue", series="series"),
            url_path_regex=rf"comics/(?P<id_type>issue|series)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="comics/{id_type}/{id_key}/s",
        ),
        IdSources.METRON: IdentifierParts(
            # Metron uses the slug for an id in most urls
            #   but can also use the numeric metron id which redirects to the slug
            # https://github.com/Metron-Project/metron/blob/master/metron/urls.py
            # Genre, location, reprint, role, story, and tag have no public web
            #   pages on metron.cloud (only API endpoints), so they're omitted
            #   here — emitting URLs for them produces 404s.
            domain="metron.cloud",
            id_type=IdentifierTypes(
                arc="arc",
                character="character",
                creator="creator",
                imprint="imprint",
                issue="issue",
                publisher="publisher",
                series="series",
                team="team",
                universe="universe",
            ),
            # id_key is a single path segment ([^/]+), so a trailing slash in
            # the url (…/issue/123495/) isn't swallowed into the captured id.
            url_path_regex=r"(?P<id_type>[^/]+)/(?P<id_key>[^/]+)/?",
            url_path_template="{id_type}/{id_key}",
        ),
        IdSources.MYANIMELIST: IdentifierParts(
            domain="myanimelist.net",
            id_type=IdentifierTypes(series="manga"),
            url_path_regex=rf"(?P<id_type>manga)/(?P<id_key>\d+){_SLUG_REXP}",
            url_path_template="{id_type}/{id_key}/s",
        ),
        IdSources.PANELSYNDICATE: IdentifierParts(
            domain="panelsyndicate.com",
            id_type=IdentifierTypes(series="comics"),
            url_path_regex=r"(?P<id_type>comics)/(?P<id_key>\w+)",
            url_path_template="{id_type}/{id_key}",
            https=False,  # :o
        ),
        IdSources.UPC: IdentifierParts(
            domain="barcodelookup.com",
            id_type=IdentifierTypes(issue="issue"),
            url_path_regex=r"(?P<id_key>[\d-]+)",
            url_path_template="{id_key}",
        ),
    }
)


def _normalize_comicvine_id_key(id_type: str, id_key: str) -> tuple:
    """I expect its quite common to list the full comicvine code in situations where only the id is necessary."""
    match = PARSE_COMICVINE_RE.match(id_key)
    if not match:
        return id_type, id_key
    try:
        id_type_code = match.group("id_type")
    except IndexError:
        return id_type, id_key
    id_type = IDENTIFIER_PARTS_MAP[IdSources.COMICVINE].get_type_by_code(
        id_type_code, id_type
    )
    with suppress(IndexError):
        id_key = match.group("id_key")
    return id_type, id_key


def normalize_key(id_source_str: str, id_type: str, id_key: str) -> tuple[str, str]:
    """
    Strip urn, source, and type prefixes off an id key.

    Hand-tagged keys often mirror the urn form comicbox writes to notes and
    GTIN (e.g. "series:178012"); a type prefix overrides the caller's id_type.
    Prefixes naming a different source are left alone. Comicvine long codes
    ("4050-160294") are normalized last.
    """
    parts = id_key.strip().split(":")
    while len(parts) > 1:
        head = parts[0].strip().lower()
        if head == "urn":
            parts.pop(0)
        elif head in _ID_TYPES:
            id_type = head
            parts.pop(0)
        else:
            head_source = get_id_source_by_alias(head, None)
            if head_source and head_source.value == id_source_str:
                parts.pop(0)
            else:
                break
    id_key = ":".join(parts).strip()
    if id_source_str == IdSources.COMICVINE.value:
        id_type, id_key = _normalize_comicvine_id_key(id_type, id_key)
    return id_type, id_key


def get_identifier_url(id_source_str: str, id_type: str, id_key: str) -> str:
    """Get a url for an identifier if we know the rest."""
    url = ""
    with suppress(ValueError):
        id_source = IdSources(id_source_str)
        if id_parts := IDENTIFIER_PARTS_MAP.get(id_source):
            url = id_parts.unparse_url(id_type, id_key)
    return url


def create_identifier(
    id_source_str: str,
    id_key: str,
    *,
    id_type: str = "",
    positional_id_type: str = DEFAULT_ID_TYPE,
    default_id_source_str: str = DEFAULT_ID_SOURCE.value,
) -> dict:
    """
    Create identifier dict from parts.

    ``id_type`` is the type the identifier string itself named, if any.
    ``positional_id_type`` is the type implied by where the identifier sits:
    an id under ``series`` is a series id. The type is stored only when the
    two disagree, because that is when it decides which url the key builds.

    Only the key is stored. A url for it is derived on demand with
    ``get_identifier_url``; keeping a synthesized copy inside the identifier
    let the two disagree and made a guessed url look like source data.
    """
    identifier = {}
    if not id_source_str:
        id_source_str = default_id_source_str
    if id_key:
        id_type, id_key = normalize_key(
            id_source_str, id_type or positional_id_type, id_key
        )
        if id_key:
            identifier[ID_KEY_KEY] = id_key
            if id_type != positional_id_type:
                # The string named a type that isn't the one where it sits.
                identifier[ID_TYPE_KEY] = id_type
    return identifier


def get_id_source_from_url(url: str) -> str:
    """Parse the id source for a url."""
    obj = urlparse(url)
    # The hostname, not the netloc: it is lowercased and carries neither the
    # port nor the userinfo, so metron.cloud:443 and Metron.Cloud both name
    # metron instead of falling through as unknown domains.
    hostname = obj.hostname or ""
    parts = hostname.split(".")

    parts.reverse()
    node = SOURCE_ALIAS_TREE
    id_source_str = hostname
    for part in parts:
        node = node.get(part)
        if isinstance(node, IdSources):
            id_source_str = node.value
            break
        if not node:
            break
    return id_source_str
