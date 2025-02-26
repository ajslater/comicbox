"""MetronInfo.xml Identifiers & URLs Transform."""

from collections.abc import Mapping
from enum import Enum

from bidict import frozenbidict

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    ISBN_NID,
    NID_ORIGIN_MAP,
    UPC_NID,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    IDENTIFIERS_KEY,
)
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.transforms.metroninfo.reprints import MetronInfoTransformReprints


class MetronInfoTransformIdentifiers(MetronInfoTransformReprints):
    """MetronInfo.xml Identifiers & URLs Transform."""

    ISBN_TAG = "ISBN"
    UPC_TAG = "UPC"
    GTIN_SUBTAGS = frozenbidict({ISBN_TAG: ISBN_NID, UPC_TAG: UPC_NID})

    @classmethod
    def parse_item_primary(cls, native_identifier) -> bool:
        """Parse primary attribute."""
        return (
            bool(native_identifier.get(cls.PRIMARY_ATTRIBUTE))
            if isinstance(native_identifier, Mapping)
            else False
        )

    @classmethod
    def parse_identifier_native(cls, native_identifier) -> tuple[str, str, str]:
        """Parse metron identifier type into components."""
        source = native_identifier.get(cls.SOURCE_ATTRIBUTE, "")  # type: ignore[reportAttributeAccessIssue]
        if isinstance(source, Enum):
            source = source.value
        nid = NID_ORIGIN_MAP.inverse.get(source, "")
        nss_type = "issue"
        nss = get_cdata(native_identifier) or "" if nid else ""
        return nid, nss_type, nss

    def parse_identifiers(self, data: dict) -> dict:
        """Hoist Identifiers before parsing."""
        return self._parse_metron_tag(data, self.IDENTIFIERS_TAG, self.parse_identifier)

    def parse_urls(self, data: dict) -> dict:
        """Parse URLs."""
        return self._parse_metron_tag(data, self.URLS_TAG, self.parse_url)

    def parse_gtin(self, data):
        """Parse complex metron gtin structure into identifiers."""
        complex_gtin = data.pop(self.GTIN_TAG, None)
        if not complex_gtin:
            return data
        comicbox_identifiers = {}
        for tag, nid in self.GTIN_SUBTAGS.items():
            if nss := complex_gtin.get(tag):
                identifier = create_identifier(nid, nss)
                comicbox_identifiers[nid] = identifier
        self.merge_identifiers(data, comicbox_identifiers)
        return data

    @classmethod
    def _unparse_gtin_from_identifier(cls, data, nid: str, nss: str):
        """Unparse GTIN from identifier as a side effect."""
        gtin_subtag = cls.GTIN_SUBTAGS.inverse.get(nid)
        if not gtin_subtag:
            return False
        if cls.GTIN_TAG not in data:
            data[cls.GTIN_TAG] = {}
        data[cls.GTIN_TAG][gtin_subtag] = nss
        return True

    @classmethod
    def unparse_url(cls, data: dict, nid: str, comicbox_identifier: dict) -> dict:
        """Unparse one identifier to an xml metron URL tag."""
        metron_url = super().unparse_url(data, nid, comicbox_identifier)

        primary_nid = cls.get_primary_source_nid(data)
        if nid == primary_nid:
            # This works here because these are added one at a time with the side effect
            metron_url[cls.PRIMARY_ATTRIBUTE] = True

        return metron_url

    @classmethod
    def _unparse_url_from_identifier(cls, data, nid, comicbox_identifier):
        """Unparse one URL from the identifier as a side effect."""
        if metron_url := cls.unparse_url(data, nid, comicbox_identifier):
            if cls.URLS_TAG not in data:
                data[cls.URLS_TAG] = []
            data[cls.URLS_TAG].append(metron_url)

    @classmethod
    def unparse_identifier(
        cls, data: dict, nid: str, comicbox_identifier: dict
    ) -> dict:
        """Unparse one identifier to an xml metron GTIN or ID tag."""
        metron_identifier = {}
        nss = comicbox_identifier.get(NSS_KEY, "")
        if (
            nss
            and (not cls._unparse_gtin_from_identifier(data, nid, nss))
            and (nid_value := NID_ORIGIN_MAP.get(nid))
        ):
            metron_identifier = {cls.SOURCE_ATTRIBUTE: nid_value, "#text": nss}
            primary_nid = cls.get_primary_source_nid(data)
            if nid == primary_nid:
                metron_identifier[cls.PRIMARY_ATTRIBUTE] = True

        # Side effects
        cls._unparse_url_from_identifier(data, nid, comicbox_identifier)
        return metron_identifier

    def unparse_identifiers(self, data: dict) -> dict:
        """Lower Identifiers after unparsing."""
        data = self._unparse_metron_tag(data, IDENTIFIERS_KEY, self.unparse_identifier)
        if urls := data.pop(self.URLS_TAG, None):
            data = self._lower_metron_tag(data, URL_KEY, urls)
        return data
