"""Identifier Fields."""

from logging import getLogger
from typing import Any
from urllib.parse import urlparse

from glom import T

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    DEFAULT_NID,
    IDENTIFIER_PARTS_MAP,
    NID_ORDER,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    NID_KEY,
)
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.transforms.transform_map import KeyTransforms, MultiAssigns
from comicbox.urns import (
    parse_string_identifier,
    to_urn_string,
)

LOG = getLogger(__name__)


def get_primary_source_nid(data, default_nid=DEFAULT_NID) -> str:
    """Get the primary source nid."""
    return data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY, default_nid)


def parse_item_primary(native_identifier) -> bool:  # noqa: ARG001
    """Parse the primary attribute from a native identifier."""
    # TODO remove
    # Overridden in metron
    return False


def create_identifier_primary_source(nid):
    """Create identifier primary source."""
    ips = {NID_KEY: nid}
    id_parts = IDENTIFIER_PARTS_MAP.get(nid)
    if id_parts and (url := id_parts.unparse_url("", "")):
        ips[URL_KEY] = url
    return ips


def parse_identifier_native(
    native_identifier: str | dict, naked_nid: str
) -> tuple[str, str, str]:
    """Parse the native identifier type into components. Defaults to string input."""
    # TODO remove
    return parse_string_identifier(native_identifier, naked_nid=naked_nid)  # type: ignore[reportArgumentType]


def _identifier_to_cb(
    native_identifier, naked_nid
) -> tuple[str, dict, None | tuple[str, Any]]:
    """Parse one identifier urn or string."""
    nid, nss_type, nss = parse_identifier_native(native_identifier, naked_nid)
    comicbox_identifier = {}
    assign: tuple[str, Any] | None = None
    if (
        not assign
        and (nid or nss)
        and T.get(IDENTIFIER_PRIMARY_SOURCE_KEY)
        and (comicbox_identifier := create_identifier(nid, nss, nss_type=nss_type))
        and parse_item_primary(native_identifier)
    ):
        ips = create_identifier_primary_source(nid)
        assign = (IDENTIFIER_PRIMARY_SOURCE_KEY, ips)
    return nid, comicbox_identifier, assign


def _identifiers_to_cb(
    _source_data, native_identifiers, naked_nid: str
) -> dict | MultiAssigns:
    """Parse identifier struct from a string or sequence."""
    comicbox_identifiers = {}
    assign: None | tuple[str, Any] = None
    for native_identifier in native_identifiers:
        try:
            nid, identifier, assign = _identifier_to_cb(native_identifier, naked_nid)
            comicbox_identifiers[nid] = identifier
        except Exception as exc:
            LOG.warning(f"Parsing identifier {native_identifier}: {exc}")
    if assign:
        result = MultiAssigns(comicbox_identifiers, extra_assigns=(assign,))
    else:
        result = comicbox_identifiers
    return result


def _identifier_from_cb(
    nid: str,
    comicbox_identifier: dict,
) -> str:
    """Usually add to comma delineated urn strings. Overridable."""
    # These are issues which is the default type.
    if nss := comicbox_identifier.get(NSS_KEY):
        return to_urn_string(nid, "", nss)
    return ""


def _identifiers_from_cb(_source_data: dict, comicbox_identifiers) -> set:
    """Unparse identifier struct to set of strings."""
    urn_strings = set()
    for nid in NID_ORDER:
        comicbox_identifier = comicbox_identifiers.get(nid)
        if not comicbox_identifier:
            continue
        if urn_dict := _identifier_from_cb(nid, comicbox_identifier):
            urn_strings.add(urn_dict)
    return urn_strings


def identifiers_transform(identifiers_tag, naked_nid):
    """Transform identifier tags to comicbox identifiers."""

    def to_cb(source_data, identifiers):
        return _identifiers_to_cb(source_data, identifiers, naked_nid)

    return KeyTransforms(
        key_map={identifiers_tag: IDENTIFIERS_KEY},
        to_cb=to_cb,
        from_cb=_identifiers_from_cb,
    )


def _parse_url(nid: str, id_parts, url: str) -> dict | None:
    """Try to parse a single nid from a url."""
    nss_type, nss = id_parts.parse_url(url)
    if not nss_type or not nss:
        return {}
    return create_identifier(nid, nss, url=url, nss_type=nss_type)


def _parse_unknown_url(url_str: str) -> tuple[str, dict]:
    """Parse unknown urls."""
    try:
        url = urlparse(url_str)
        nid = url.netloc
        nss = ""
        if url.path:
            nss += url.path
        if url.query:
            nss += "?" + url.query
        if url.fragment:
            nss += "#" + url.fragment
        identifier = {NSS_KEY: nss, URL_KEY: url_str}
    except Exception:
        LOG.debug(f"Unparsable url: {url_str}")
        nid = ""
        identifier = {}
    return nid, identifier


def url_to_cb(
    native_url: str | dict,
) -> tuple[str, dict]:
    """Parse one url into identifier."""
    url_str = get_cdata(native_url)
    if not url_str:
        return "", {}
    for nid, id_parts in IDENTIFIER_PARTS_MAP.items():
        if identifier := _parse_url(nid, id_parts, url_str):
            break
    else:
        nid, identifier = _parse_unknown_url(url_str)
    return nid, identifier


def urls_to_cb(_source_data, urls):
    """Parse url tags into identifiers."""
    comicbox_identifiers = {}
    for url in urls:
        nid, identifier = url_to_cb(url)
        if nid or identifier:
            comicbox_identifiers[nid] = identifier
    return comicbox_identifiers


def url_from_cb(
    nid: str,
    comicbox_identifier: dict,
) -> str:
    """Unparse one identifier into one url tag."""
    url = comicbox_identifier.get(URL_KEY, "")
    if not url and (nss := comicbox_identifier.get(NSS_KEY)):
        new_identifier = create_identifier(nid, nss)
        url = new_identifier.get(URL_KEY, "")
    return url


def _urls_from_cb(_source_data: dict, comicbox_identifiers) -> set:
    """Unparse urls struct to set of strings."""
    url_strings = set()
    for nid, comicbox_identifier in comicbox_identifiers.items():
        if url := url_from_cb(nid, comicbox_identifier):
            url_strings.add(url)
    return url_strings


def urls_transform(urls_tag):
    """Transform urls tags to comicbox identifiers."""
    return KeyTransforms(
        key_map={urls_tag: IDENTIFIERS_KEY}, to_cb=urls_to_cb, from_cb=_urls_from_cb
    )
