"""Comicbox computed identifiers."""

from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.formats import MetadataFormats
from comicbox.identifiers.const import (
    DEFAULT_NID,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    NID_ORDER,
    NSS_KEY,
    URL_KEY,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
)
from comicbox.identifiers.other import (
    parse_identifier_str,
)
from comicbox.identifiers.urns import (
    parse_urn_identifier,
)
from comicbox.merge import AdditiveMerger
from comicbox.schemas.comicbox import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    TAGS_KEY,
)
from comicbox.transforms.identifiers import create_identifier_primary_source


class ComicboxComputedIdentifers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    def _get_computed_from_tags(self, sub_data):
        if not sub_data or TAGS_KEY in self._config.delete_keys:
            return None
        tags = sub_data.get(TAGS_KEY)
        if not tags:
            return None
        identifiers = {}
        for tag in tags:
            # Silently fail because most tags are not identifiers
            nid, _, nss = parse_urn_identifier(tag)
            if not (nid and nss):
                nid, _, nss = parse_identifier_str(tag)
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
                if nss:
                    identifiers[nid] = create_identifier(nid, nss)
        if not identifiers:
            return None
        return {IDENTIFIERS_KEY: identifiers}

    def _add_urls_to_identifiers(self, identifiers):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        identifiers_with_urls = {}
        for nid, identifier in identifiers.items():
            if identifier.get(URL_KEY):
                continue
            if nss := identifier.get(NSS_KEY):
                new_identifier = create_identifier(nid, nss)
                identifiers_with_urls[nid] = new_identifier
        return identifiers_with_urls

    def _add_identifier_primary_source_key(self, sub_data, identifiers):
        if (
            IDENTIFIER_PRIMARY_SOURCE_KEY in self._config.delete_keys
            or not (
                self._config.write
                & frozenset({MetadataFormats.COMICTAGGER, MetadataFormats.METRON_INFO})
            )
            or sub_data.get(IDENTIFIER_PRIMARY_SOURCE_KEY)
        ):
            return None
        for nid in NID_ORDER:
            if nid in identifiers and (ips := create_identifier_primary_source(nid)):
                return ips
        return None

    def _get_computed_from_identifiers(self, sub_data):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        identifiers = sub_data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return None
        result = {}
        if identifiers_with_added_urls := self._add_urls_to_identifiers(identifiers):
            result[IDENTIFIERS_KEY] = identifiers_with_added_urls
        if ips := self._add_identifier_primary_source_key(sub_data, identifiers):
            result[IDENTIFIER_PRIMARY_SOURCE_KEY] = ips
        if not result:
            return None
        return result

    COMPUTED_ACTIONS = MappingProxyType(
        {
            **ComicboxComputedIssue.COMPUTED_ACTIONS,
            "from tags": (_get_computed_from_tags, AdditiveMerger),
            "from identifiers": (_get_computed_from_identifiers, AdditiveMerger),
        }
    )
