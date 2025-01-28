"""Identifier Fields."""

from collections.abc import Sequence
from logging import getLogger
from re import Pattern
from urllib.parse import urlparse

from comicbox.identifiers import (
    NID_ORDER,
    WEB_REGEX_URLS,
    create_identifier,
    parse_identifier,
    to_urn_string,
)
from comicbox.schemas.comicbox_mixin import IDENTIFIERS_KEY
from comicbox.schemas.identifier import NSS_KEY, URL_KEY

LOG = getLogger(__name__)


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
    IDENTIFIERS_SUB_TAG = ""
    NAKED_NID = None
    URL_TAG = ""

    def parse_identifier(self, item):
        """Parse one identifier urn or string."""
        return parse_identifier(item, naked_nid=self.NAKED_NID)

    def parse_extracted_identifiers(self, identifiers) -> dict:
        """Parse extracted identifier sequence to a map."""
        if not isinstance(identifiers, Sequence | set | frozenset):
            return identifiers
        # Allow multiple identifiers from xml, etc.
        # Technically out of spec.
        identifier_map = {}
        for item in identifiers:
            nid, nss = self.parse_identifier(item)

            if nid and nss:
                identifier = create_identifier(nid, nss)
                identifier_map[nid] = identifier

        return identifier_map

    def parse_identifiers(self, data: dict):
        """Parse identifier struct from a string or sequence."""
        identifiers = data.pop(self.IDENTIFIERS_TAG, None)
        if not identifiers:
            return data
        if self.IDENTIFIERS_SUB_TAG:
            identifiers = identifiers.pop(self.IDENTIFIERS_SUB_TAG, None)
        if not identifiers:
            return data
        identifiers = self.parse_extracted_identifiers(identifiers)

        if identifiers:
            if IDENTIFIERS_KEY not in data:
                data[IDENTIFIERS_KEY] = {}
            data[IDENTIFIERS_KEY].update(identifiers)
        return data

    def unparse_url_tag(self, data: dict, nid: str, nss: str, url: str | None) -> dict:
        """Unparse one identifier into one url tag."""
        if not self.URL_TAG:
            return data

        if not url:
            new_identifier = create_identifier(nid, nss)
            url = new_identifier.get(URL_KEY)

        if not url:
            return data

        if self.URL_TAG not in data:
            data[self.URL_TAG] = ""
        add_url = "," + url if data[self.URL_TAG] else url
        data[self.URL_TAG] += add_url
        return data

    def unparse_identifier(self, data: dict, nid: str, nss: str):
        """Usually add to comma dilneated urn strings. Overridable."""
        urn_string = to_urn_string(nid, nss)
        if not urn_string:
            return data
        if self.IDENTIFIERS_TAG not in data:
            data[self.IDENTIFIERS_TAG] = ""
        else:
            urn_string = urn_string + ","

        data[self.IDENTIFIERS_TAG] += urn_string

        return data

    def unparse_identifiers(self, data: dict):
        """Unparse identifier struct to a string."""
        if not self.IDENTIFIERS_TAG:
            return data
        identifiers = data.pop(IDENTIFIERS_KEY, {})
        if not identifiers:
            return data
        for nid in NID_ORDER:
            identifier = identifiers.get(nid)
            if not identifier:
                continue
            if nss := identifier.get(NSS_KEY):
                data = self.unparse_identifier(data, nid, nss)
            url = identifiers.get(URL_KEY)
            if url or nss:
                data = self.unparse_url_tag(data, nid, nss, url)
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
