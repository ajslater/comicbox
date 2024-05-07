"""Identifier Fields."""

from collections.abc import Sequence
from logging import getLogger
from re import Pattern
from urllib.parse import urlparse

from comicbox.identifiers import (
    GTIN_NID_ORDER,
    IDENTIFIER_URL_MAP,
    WEB_REGEX_URLS,
    create_identifier,
    parse_identifier,
    to_urn_string,
)
from comicbox.schemas.comicbox_mixin import IDENTIFIERS_KEY
from comicbox.schemas.identifier import NSS_KEY, URL_KEY

LOG = getLogger(__name__)


def _sequence_to_map(identifier_sequence, naked_nid=None):
    if not isinstance(identifier_sequence, Sequence | set | frozenset):
        return identifier_sequence
    # Allow multiple identifiers from xml, etc.
    # Technically out of spec.
    identifier_map = {}
    for item in identifier_sequence:
        nid, nss = parse_identifier(item, naked_nid=naked_nid)

        if nid and nss:
            identifier = create_identifier(nid, nss)
            identifier_map[nid] = identifier

    return identifier_map


def _parse_url_tag_nid(nid: str, regex: Pattern, url: str, data: dict) -> bool:
    """Try to parse a single nid from a url."""
    match = regex.search(url)
    if not match:
        return False
    nss = match.group("identifier")
    if not nss:
        return False
    identifier = create_identifier(nid, nss, url)
    if IDENTIFIERS_KEY not in data:
        data[IDENTIFIERS_KEY] = {}
    if nid not in data[IDENTIFIERS_KEY]:
        data[IDENTIFIERS_KEY][nid] = {}
    data[IDENTIFIERS_KEY][nid] = identifier
    return True


def _parse_unknown_url(url_str: str, data: dict) -> None:
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
        if IDENTIFIERS_KEY not in data:
            data[IDENTIFIERS_KEY] = {}
        data[IDENTIFIERS_KEY][nid] = identifier
    except Exception:
        LOG.debug(f"Unparsable url: {url_str}")


class IdentifiersTransformMixin:
    """Transform Identifiers."""

    IDENTIFIERS_TAG = ""
    NAKED_NID = None
    URL_TAG = ""

    def parse_identifiers(self, data: dict):
        """Parse identifier struct from a string or sequence."""
        identifiers = data.pop(self.IDENTIFIERS_TAG, None)
        if not identifiers:
            return data
        identifiers = _sequence_to_map(identifiers, naked_nid=self.NAKED_NID)
        if identifiers:
            data[IDENTIFIERS_KEY] = identifiers
        return data

    def unparse_identifiers(self, data: dict):
        """Unparse identifier struct to a string."""
        identifiers = data.pop(IDENTIFIERS_KEY, {})
        if not identifiers:
            return data
        for nid in GTIN_NID_ORDER:
            if nss := identifiers.get(nid, {}).get(NSS_KEY):
                break
        else:
            return data
        if not nid or not nss:
            return data
        data[self.IDENTIFIERS_TAG] = to_urn_string(
            nid,
            nss,
        )
        return data

    def parse_url_tag(self, data):
        """Parse url tags into identifiers."""
        if urls := data.get(self.URL_TAG):
            urls = (urls,) if isinstance(urls, str) else tuple(sorted(urls))
            for url in urls:
                for nid, regex in WEB_REGEX_URLS.items():
                    if _parse_url_tag_nid(nid, regex, url, data):
                        break
                else:
                    _parse_unknown_url(url, data)
        return data

    def unparse_url_tag(self, data):
        """Unparse identifier url into url tag."""
        if not self.URL_TAG:
            return data
        if identifiers := data.get(IDENTIFIERS_KEY):
            for nid in IDENTIFIER_URL_MAP:
                identifier = identifiers.get(nid)
                if not identifier:
                    continue
                url = identifier.get(URL_KEY)
                if not url:
                    nss = identifier.get(NSS_KEY)
                    new_identifier = create_identifier(nid, nss)
                    url = new_identifier.get(URL_KEY)
                if url:
                    data[self.URL_TAG] = url
                    break
            else:
                # Get first unknown url
                identifier = next(iter(identifiers.values()))
                if url := identifier.get(URL_KEY):
                    data[self.URL_TAG] = url

        return data
