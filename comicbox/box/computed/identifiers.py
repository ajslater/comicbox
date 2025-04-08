"""Comicbox computed identifiers."""

from logging import getLogger
from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.formats import MetadataFormats
from comicbox.identifiers import (
    DEFAULT_NID,
    NID_ORDER,
    NSS_KEY,
    URL_KEY,
    create_identifier,
)
from comicbox.merge import AdditiveMerger
from comicbox.schemas.comicbox import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    TAGS_KEY,
)
from comicbox.schemas.comictagger import ISSUE_ID_KEY, SERIES_ID_KEY, TAG_ORIGIN_KEY
from comicbox.transforms.identifiers import create_identifier_primary_source
from comicbox.urns import (
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    parse_urn_identifier,
)

LOG = getLogger(__name__)


class ComicboxComputedIdentifers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    def _get_computed_from_tags(self, sub_data):
        if not sub_data:
            return None

        tags = sub_data.get(TAGS_KEY)
        if not tags:
            return None
        identifiers = {}
        for tag in tags:
            # Silently fail because most tags are not urns
            nid, _, nss = parse_urn_identifier(tag)
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
                if nss:
                    identifiers[nid] = create_identifier(nid, nss)
        return identifiers

    def _add_urls_to_identifiers(self, sub_data):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        if not identifiers:
            return None
        identifiers_with_urls = {}
        for nid, identifier in identifiers.items():
            if identifier.get(URL_KEY):
                continue
            if nss := identifier.get(NSS_KEY):
                new_identifier = create_identifier(nid, nss)
                identifiers_with_urls[nid] = new_identifier
        return identifiers_with_urls

    def _add_identifier_primary_source_key(self, sub_data):
        ips = {}
        if {IDENTIFIERS_KEY, IDENTIFIER_PRIMARY_SOURCE_KEY} & {
            self._config.delete_keys
        }:
            return ips
        if not (
            self._config.write
            & {MetadataFormats.COMICTAGGER, MetadataFormats.METRON_INFO}
        ):
            return ips
        identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        if sub_data.get(IDENTIFIER_PRIMARY_SOURCE_KEY) or not identifiers:
            return ips
        for nid in NID_ORDER:
            if nid in identifiers:
                ips = create_identifier_primary_source(nid)
                break
        return ips

    def _get_computed_from_identifiers(self, sub_data):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        result = {}
        if identifiers_with_urls := self._add_urls_to_identifiers(sub_data):
            result[IDENTIFIERS_KEY] = identifiers_with_urls
        if ips := self._add_identifier_primary_source_key(sub_data):
            result[IDENTIFIER_PRIMARY_SOURCE_KEY] = ips
        if result:
            return result
        return None

    def _get_computed_from_tag_origin(self, sub_data):
        # Should this pop or should it pop on ct post load?
        if IDENTIFIERS_KEY in self._config.delete_keys or not sub_data:
            return None
        nid = sub_data.pop(TAG_ORIGIN_KEY, {}).get("id", "")
        nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
        if not nid:
            return None
        nss = sub_data.pop(ISSUE_ID_KEY, None)
        if not nss:
            nss = sub_data.pop(SERIES_ID_KEY, None)
            if not nss:
                return None
        return {nid: nss}

    COMPUTED_ACTIONS = MappingProxyType(
        {
            **ComicboxComputedIssue.COMPUTED_ACTIONS,
            "from tags": (_get_computed_from_tags, AdditiveMerger),
            "from identifiers": (_get_computed_from_identifiers, AdditiveMerger),
            "from tag_origin": (_get_computed_from_tag_origin, AdditiveMerger),
        }
    )
