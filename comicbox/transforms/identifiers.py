"""Identifier Fields."""

from logging import getLogger
from urllib.parse import urlparse

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers.const import (
    NSS_KEY,
    URL_KEY,
    NIDs,
)
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
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    NID_KEY,
)
from comicbox.transforms.spec import MetaSpec

LOG = getLogger(__name__)

PRIMARY_NID_KEYPATH = f"{IDENTIFIER_PRIMARY_SOURCE_KEY}.{NID_KEY}"


def create_identifier_primary_source(nid):
    """Create identifier primary source."""
    ips = {NID_KEY: nid}
    id_parts = IDENTIFIER_PARTS_MAP.get(nid)
    if id_parts and (url := id_parts.unparse_url("", "")):
        ips[URL_KEY] = url
    return ips


def _identifier_to_cb(native_identifier, naked_nid) -> tuple[str, dict]:
    """Parse one identifier urn or string."""
    nid, nss_type, nss = parse_string_identifier(native_identifier, naked_nid)
    comicbox_identifier = create_identifier(
        nid, nss, nss_type=nss_type, default_nid=naked_nid
    )
    return nid, comicbox_identifier


def identifiers_to_cb(native_identifiers, naked_nid: str) -> dict:
    """Parse identifier struct from a string or sequence."""
    comicbox_identifiers = {}
    if native_identifiers:
        for native_identifier in native_identifiers:
            try:
                nid, identifier = _identifier_to_cb(native_identifier, naked_nid)
                comicbox_identifiers[nid] = identifier
            except Exception as exc:
                LOG.warning(f"Parsing identifier {native_identifier}: {exc}")
    return comicbox_identifiers


def identifiers_transform_to_cb(identifiers_tag, naked_nid):
    """Transform identifier tags to comicbox identifiers."""

    def to_cb(native_identifiers):
        return identifiers_to_cb(native_identifiers, naked_nid)

    return MetaSpec(
        key_map={IDENTIFIERS_KEY: identifiers_tag},
        spec=to_cb,
    )


def _identifiers_from_cb(comicbox_identifiers) -> set:
    """Unparse identifier struct to set of strings."""
    urn_strings = set()
    for nid in NIDs:
        if (
            (comicbox_identifier := comicbox_identifiers.get(nid.value))
            and (nss := comicbox_identifier.get(NSS_KEY))
            and (urn_str := to_urn_string(nid.value, "", nss))
        ):
            urn_strings.add(urn_str)
    return urn_strings


def identifiers_transform_from_cb(identifiers_tag):
    """Transform comicbox identifiers identifier tag."""
    return MetaSpec(
        key_map={identifiers_tag: IDENTIFIERS_KEY},
        spec=_identifiers_from_cb,
    )


def _parse_url(nid: str, id_parts: IdentifierParts, url: str) -> dict | None:
    """Try to parse a single nid from a url."""
    nss_type, nss = id_parts.parse_url(url)
    if not nss_type or not nss:
        # iterating over all nids so fail if not perfect.
        return {}
    return create_identifier(nid, nss, url=url, nss_type=nss_type)


def _parse_unknown_url(url_str: str) -> tuple[str, dict]:
    """Parse unknown urls."""
    identifier = {}
    try:
        url = urlparse(url_str)
        nid = url.netloc
        nss = ""
        if url.path and url.path != "/":
            nss += url.path
        if url.query:
            nss += "?" + url.query
        if url.fragment:
            nss += "#" + url.fragment
        if nss:
            identifier[NSS_KEY] = nss
        if url:
            identifier[URL_KEY] = url_str
    except Exception:
        LOG.debug(f"Unparsable url: {url_str}")
        nid = ""
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


def urls_to_cb(urls):
    """Parse url tags into identifiers."""
    comicbox_identifiers = {}
    if urls:
        for url in urls:
            nid, identifier = url_to_cb(url)
            if nid or identifier:
                comicbox_identifiers[nid] = identifier
    return comicbox_identifiers


def urls_transform_to_cb(urls_tag):
    """Transform urls tags to comicbox identifiers."""
    return MetaSpec(
        key_map={IDENTIFIERS_KEY: urls_tag},
        spec=urls_to_cb,
    )


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


def _urls_from_cb(comicbox_identifiers) -> set:
    """Unparse urls struct to set of strings."""
    url_strings = set()
    for nid, comicbox_identifier in comicbox_identifiers.items():
        if url := url_from_cb(nid, comicbox_identifier):
            url_strings.add(url)
    return url_strings


def urls_transform_from_cb(urls_tag):
    """Transform comicbox identifiers to urls tags."""
    return MetaSpec(key_map={urls_tag: IDENTIFIERS_KEY}, spec=_urls_from_cb)
