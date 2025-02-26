"""Identifier Fields."""

from collections.abc import Sequence
from logging import getLogger
from urllib.parse import urlparse

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

    @staticmethod
    def get_primary_source_nid(data) -> str:
        """Get the primary source nid."""
        return data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY, DEFAULT_NID)

    @staticmethod
    def parse_item_primary(native_identifier) -> bool:  # noqa: ARG004
        """Parse if an item has a primary attribute."""
        return False

    @staticmethod
    def assign_identifier_primary_source(data, nid):
        """Assign identifier primary source."""
        ips = {NID_KEY: nid}
        id_parts = IDENTIFIER_PARTS_MAP.get(nid)
        if id_parts and (url := id_parts.unparse_url("", "")):
            ips[URL_KEY] = url
        data[IDENTIFIER_PRIMARY_SOURCE_KEY] = ips

    @staticmethod
    def merge_identifiers(data: dict, comicbox_identifiers: dict):
        """Merge parsed identifiers with the currently assigned identifiers."""
        if not comicbox_identifiers:
            return
        merged_identifiers = data.get(IDENTIFIERS_KEY, {})
        merged_identifiers.update(comicbox_identifiers)
        data[IDENTIFIERS_KEY] = merged_identifiers

    def parse_identifier_native(
        self, native_identifier: str | dict
    ) -> tuple[str, str, str]:
        """Parse the native identifier type into components. Defaults to string input."""
        return parse_string_identifier(native_identifier, naked_nid=self.NAKED_NID)  # type: ignore[reportArgumentType]

    def parse_identifier(self, data, native_identifier) -> tuple[str, dict]:
        """Parse one identifier urn or string."""
        nid, nss_type, nss = self.parse_identifier_native(native_identifier)
        comicbox_identifier = {}
        if (
            (nid or nss)
            and (comicbox_identifier := create_identifier(nid, nss, nss_type=nss_type))
            and IDENTIFIER_PRIMARY_SOURCE_KEY not in data
            and self.parse_item_primary(native_identifier)
        ):
            self.assign_identifier_primary_source(data, nid)
        return nid, comicbox_identifier

    def parse_identifiers(self, data: dict) -> dict:
        """Parse identifier struct from a string or sequence."""
        native_identifiers = data.pop(self.IDENTIFIERS_TAG, None)
        if not native_identifiers or not isinstance(
            native_identifiers, Sequence | set | frozenset
        ):
            return data
        # Allow multiple identifiers from xml, etc.
        # Technically out of spec.
        comicbox_identifiers = {}
        for native_identifier in native_identifiers:
            try:
                nid, identifier = self.parse_identifier(data, native_identifier)
                comicbox_identifiers[nid] = identifier
            except Exception as exc:
                LOG.warning(f"Parsing identifier {native_identifier}: {exc}")
        if comicbox_identifiers:
            data[IDENTIFIERS_KEY] = comicbox_identifiers

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

    def parse_url(
        self,
        data: dict,  # noqa: ARG002
        native_url: str | dict,
    ) -> tuple[str, dict]:
        """Parse one url into identifier."""
        url_str = get_cdata(native_url)
        if not url_str:
            return "", {}
        for nid, id_parts in IDENTIFIER_PARTS_MAP.items():
            if identifier := self._parse_url(nid, id_parts, url_str):
                break
        else:
            nid, identifier = self._parse_unknown_url(url_str)
        return nid, identifier

    def parse_urls(self, data):
        """Parse url tags into identifiers."""
        urls = data.pop(self.URLS_TAG, [])
        comicbox_identifiers = {}
        for url in urls:
            nid, identifier = self.parse_url(data, url)
            if nid or identifier:
                comicbox_identifiers[nid] = identifier
        self.merge_identifiers(data, comicbox_identifiers)
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

    def unparse_identifier(
        self,
        data: dict,  # noqa: ARG002
        nid: str,
        comicbox_identifier: dict,
    ) -> dict:
        """Usually add to comma delineated urn strings. Overridable."""
        # These are issues which is the default type.
        native_identifier = {}
        if (nss := comicbox_identifier.get(NSS_KEY)) and (
            urn_str := to_urn_string(nid, "", nss)
        ):
            native_identifier["#text"] = urn_str
        return native_identifier

    def unparse_url(
        self,
        data: dict,  # noqa: ARG002
        nid: str,
        comicbox_identifier: dict,
    ) -> dict:
        """Unparse one identifier into one url tag."""
        url = comicbox_identifier.get(URL_KEY)
        if not url and (nss := comicbox_identifier.get(NSS_KEY)):
            new_identifier = create_identifier(nid, nss)
            url = new_identifier.get(URL_KEY)
        native_url = {}
        if url:
            native_url["#text"] = url
        return native_url

    def unparse_identifiers(self, data: dict) -> dict:
        """Unparse identifier struct to a string."""
        if not self.IDENTIFIERS_TAG and not self.URLS_TAG:
            return data
        comicbox_identifiers = data.pop(IDENTIFIERS_KEY, {})
        if not comicbox_identifiers:
            return data
        urn_strings = set()
        url_strings = set()
        for nid in NID_ORDER:
            comicbox_identifier = comicbox_identifiers.get(nid)
            if not comicbox_identifier:
                continue
            if self.IDENTIFIERS_TAG and (
                urn_dict := self.unparse_identifier(data, nid, comicbox_identifier)
            ):
                urn_strings.add(urn_dict.get("#text"))
            if self.URLS_TAG and (
                url_dict := self.unparse_url(data, nid, comicbox_identifier)
            ):
                url_strings.add(url_dict.get("#text"))

        if urn_strings:
            urn_strings = data.get(self.IDENTIFIERS_TAG, set()) | urn_strings
            data[self.IDENTIFIERS_TAG] = urn_strings
        if url_strings:
            url_strings = data.get(self.URLS_TAG, set()) | url_strings
            data[self.URLS_TAG] = url_strings
        return data
