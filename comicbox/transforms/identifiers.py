"""Identifier Fields."""

from collections.abc import Sequence
from logging import getLogger
from urllib.parse import urlparse

from comicbox.identifiers import (
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
from comicbox.urns import (
    parse_string_identifier,
    to_urn_string,
)

LOG = getLogger(__name__)


class IdentifiersTransformMixin:
    """Transform Identifiers."""

    IDENTIFIERS_TAG = ""
    NAKED_NID = None
    URLS_TAG = ""

    def parse_identifier(self, item) -> tuple[str, str, str]:
        """Parse one identifier urn or string."""
        return parse_string_identifier(item, naked_nid=self.NAKED_NID)

    @staticmethod
    def assign_identifier_primary_source(data, nid):
        """Assign identifier primary source."""
        ips = {NID_KEY: nid}
        id_parts = IDENTIFIER_PARTS_MAP.get(nid)
        if id_parts and (url := id_parts.unparse_url("", "")):
            ips[URL_KEY] = url
        data[IDENTIFIER_PRIMARY_SOURCE_KEY] = ips

    def parse_assign_identifier(self, data, nid, identifier, primary):
        """Assign identifier by nid."""
        if IDENTIFIERS_KEY not in data:
            data[IDENTIFIERS_KEY] = {}
        data[IDENTIFIERS_KEY][nid] = identifier
        if primary and IDENTIFIER_PRIMARY_SOURCE_KEY not in data:
            self.assign_identifier_primary_source(data, nid)

    @staticmethod
    def parse_item_primary(item) -> bool:  # noqa: ARG004
        """Parse if an item has a primary attribute."""
        return False

    def _parse_extracted_identifiers(self, data: dict, identifiers) -> None:
        """Parse extracted identifier sequence to a map."""
        if not isinstance(identifiers, Sequence | set | frozenset):
            return
        # Allow multiple identifiers from xml, etc.
        # Technically out of spec.
        for item in identifiers:
            nid, nss_type, nss = self.parse_identifier(item)
            if not nid or not nss:
                continue

            if identifier := create_identifier(nid, nss):
                primary = self.parse_item_primary(item)
                self.parse_assign_identifier(data, nid, identifier, primary)

    def parse_identifiers(self, data: dict) -> dict:
        """Parse identifier struct from a string or sequence."""
        identifiers = data.pop(self.IDENTIFIERS_TAG, None)
        if not identifiers:
            return data
        self._parse_extracted_identifiers(data, identifiers)

        return data

    @staticmethod
    def _parse_url(nid: str, id_parts, url: str) -> dict | None:
        """Try to parse a single nid from a url."""
        nss_type, nss = id_parts.parse_url(url)
        if not nss_type or not nss:
            return {}
        return create_identifier(nid, nss, url=url, nss_type=nss_type)

    @staticmethod
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

    def parse_url(self, data, url):
        """Parse one url into identifier."""
        if not url:
            return
        for nid, id_parts in IDENTIFIER_PARTS_MAP.items():
            if identifier := self._parse_url(nid, id_parts, url):
                break
        else:
            nid, identifier = self._parse_unknown_url(url)
        if identifier:
            primary = self.parse_item_primary(url)
            self.parse_assign_identifier(data, nid, identifier, primary)

    def parse_urls(self, data):
        """Parse url tags into identifiers."""
        urls = data.pop(self.URLS_TAG, None)
        if not urls:
            return data
        if not urls:
            return data
        if isinstance(urls, frozenset | set | tuple | list):
            urls = tuple(sorted(urls, key=lambda d: tuple(d)))
        else:
            urls = (urls,)
        for url in urls:
            self.parse_url(data, url)
        return data

    def parse_default_primary_identifier(self, data):
        """Parse the default primary identifiers."""
        if IDENTIFIER_PRIMARY_SOURCE_KEY in data:
            return data
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return data
        for nid in NID_ORDER:
            if nid in identifiers:
                self.assign_identifier_primary_source(data, nid)
                break
        return data

    def unparse_identifier(self, data: dict, nid: str, nss: str, primary: bool) -> dict:  # noqa: ARG002
        """Usually add to comma delineated urn strings. Overridable."""
        # These are issues which is the default type.
        nss_type = ""
        urn_string = to_urn_string(nid, nss_type, nss)
        if not urn_string:
            return data
        if self.IDENTIFIERS_TAG not in data:
            data[self.IDENTIFIERS_TAG] = ""
        else:
            urn_string = urn_string + ","

        data[self.IDENTIFIERS_TAG] += urn_string

        return data

    def unparse_url(
        self,
        data: dict,
        nid: str,
        nss: str,
        url: str | None,
        primary: bool,  # noqa: ARG002
    ) -> dict:
        """Unparse one identifier into one url tag."""
        if not self.URLS_TAG:
            return data

        if not url:
            new_identifier = create_identifier(nid, nss)
            url = new_identifier.get(URL_KEY)

        if not url:
            return data

        if self.URLS_TAG not in data:
            data[self.URLS_TAG] = ""
        add_url = "," + url if data[self.URLS_TAG] else url
        data[self.URLS_TAG] += add_url
        return data

    def unparse_identifiers(self, data: dict):
        """Unparse identifier struct to a string."""
        if not self.IDENTIFIERS_TAG:
            return data
        identifiers = data.pop(IDENTIFIERS_KEY, {})
        if not identifiers:
            return data
        primary_nid = data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY)
        for nid in NID_ORDER:
            identifier = identifiers.get(nid)
            if not identifier:
                continue
            if not primary_nid:
                primary_nid = nid
            primary = nid == primary_nid
            if nss := identifier.get(NSS_KEY):
                data = self.unparse_identifier(data, nid, nss, primary)
            url = identifiers.get(URL_KEY)
            if url or nss:
                data = self.unparse_url(data, nid, nss, url, primary)
        return data
