"""Identifier Fields."""

from urllib.parse import urlparse

from loguru import logger

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import IdSources
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
    IdentifierParts,
    create_identifier,
)
from comicbox.identifiers.urns import (
    parse_string_identifier,
    to_urn_string,
)
from comicbox.schemas.comicbox import (
    ID_KEY_KEY,
    ID_SOURCE_KEY,
    ID_URL_KEY,
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
)
from comicbox.transforms.spec import MetaSpec

PRIMARY_ID_SOURCE_KEYPATH = f"{IDENTIFIER_PRIMARY_SOURCE_KEY}.{ID_SOURCE_KEY}"


def create_identifier_primary_source(id_source):
    """Create identifier primary source."""
    ips = {ID_SOURCE_KEY: id_source}
    id_parts = IDENTIFIER_PARTS_MAP.get(id_source)
    if id_parts and (url := id_parts.unparse_url("", "")):
        ips[ID_URL_KEY] = url
    return ips


def _identifier_to_cb(native_identifier, naked_id_source) -> tuple[str, dict]:
    """Parse one identifier urn or string."""
    id_source, id_type, id_key = parse_string_identifier(
        native_identifier, naked_id_source
    )
    comicbox_identifier = create_identifier(
        id_source, id_key, id_type=id_type, default_id_source=naked_id_source
    )
    return id_source, comicbox_identifier


def identifiers_to_cb(native_identifiers, naked_id_source: str) -> dict:
    """Parse identifier struct from a string or sequence."""
    comicbox_identifiers = {}
    if native_identifiers:
        for native_identifier in native_identifiers:
            try:
                id_source, identifier = _identifier_to_cb(
                    native_identifier, naked_id_source
                )
                comicbox_identifiers[id_source] = identifier
            except Exception as exc:
                logger.warning(f"Parsing identifier {native_identifier}: {exc}")
    return comicbox_identifiers


def identifiers_transform_to_cb(identifiers_tag, naked_id_source):
    """Transform identifier tags to comicbox identifiers."""

    def to_cb(native_identifiers):
        return identifiers_to_cb(native_identifiers, naked_id_source)

    return MetaSpec(
        key_map={IDENTIFIERS_KEY: identifiers_tag},
        spec=to_cb,
    )


def _identifiers_from_cb(comicbox_identifiers) -> set:
    """Unparse identifier struct to set of strings."""
    urn_strings = set()
    for id_source in IdSources:
        if (
            (comicbox_identifier := comicbox_identifiers.get(id_source.value))
            and (id_key := comicbox_identifier.get(ID_KEY_KEY))
            and (urn_str := to_urn_string(id_source.value, "", id_key))
        ):
            urn_strings.add(urn_str)
    return urn_strings


def identifiers_transform_from_cb(identifiers_tag):
    """Transform comicbox identifiers identifier tag."""
    return MetaSpec(
        key_map={identifiers_tag: IDENTIFIERS_KEY},
        spec=_identifiers_from_cb,
    )


def _parse_url(id_source: str, id_parts: IdentifierParts, url: str) -> dict | None:
    """Try to parse a single id_source from a url."""
    id_type, id_key = id_parts.parse_url(url)
    if not id_type or not id_key:
        # iterating over all id_sources so fail if not perfect.
        return {}
    return create_identifier(id_source, id_key, url=url, id_type=id_type)


def _parse_unknown_url(url_str: str) -> tuple[str, dict]:
    """Parse unknown urls."""
    identifier = {}
    try:
        url = urlparse(url_str)
        id_source = url.netloc
        id_key = ""
        if url.path and url.path != "/":
            id_key += url.path
        if url.query:
            id_key += "?" + url.query
        if url.fragment:
            id_key += "#" + url.fragment
        if id_key:
            identifier[ID_KEY_KEY] = id_key
        if url:
            identifier[ID_URL_KEY] = url_str
    except Exception:
        logger.debug(f"Unparsable url: {url_str}")
        id_source = ""
    return id_source, identifier


def url_to_cb(
    native_url: str | dict,
) -> tuple[str, dict]:
    """Parse one url into identifier."""
    url_str = get_cdata(native_url)
    if not url_str:
        return "", {}
    for id_source, id_parts in IDENTIFIER_PARTS_MAP.items():
        if identifier := _parse_url(id_source, id_parts, url_str):
            break
    else:
        id_source, identifier = _parse_unknown_url(url_str)
    return id_source, identifier


def urls_to_cb(urls):
    """Parse url tags into identifiers."""
    comicbox_identifiers = {}
    if urls:
        for url in urls:
            id_source, identifier = url_to_cb(url)
            if id_source or identifier:
                comicbox_identifiers[id_source] = identifier
    return comicbox_identifiers


def urls_transform_to_cb(urls_tag):
    """Transform urls tags to comicbox identifiers."""
    return MetaSpec(
        key_map={IDENTIFIERS_KEY: urls_tag},
        spec=urls_to_cb,
    )


def url_from_cb(
    id_source: str,
    comicbox_identifier: dict,
) -> str:
    """Unparse one identifier into one url tag."""
    url = comicbox_identifier.get(ID_URL_KEY, "")
    if not url and (id_key := comicbox_identifier.get(ID_KEY_KEY)):
        new_identifier = create_identifier(id_source, id_key)
        url = new_identifier.get(ID_URL_KEY, "")
    return url


def _urls_from_cb(comicbox_identifiers) -> set:
    """Unparse urls struct to set of strings."""
    url_strings = set()
    for id_source, comicbox_identifier in comicbox_identifiers.items():
        if url := url_from_cb(id_source, comicbox_identifier):
            url_strings.add(url)
    return url_strings


def urls_transform_from_cb(urls_tag):
    """Transform comicbox identifiers to urls tags."""
    return MetaSpec(key_map={urls_tag: IDENTIFIERS_KEY}, spec=_urls_from_cb)
