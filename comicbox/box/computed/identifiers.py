"""Comicbox computed identifiers."""

from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.formats import MetadataFormats
from comicbox.identifiers.const import (
    ALIAS_NID_MAP,
    DEFAULT_NID,
    NIDs,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
)
from comicbox.identifiers.other import (
    parse_identifier_other_str,
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

_FORMATS_WITH_IPS = frozenset(
    {MetadataFormats.COMICTAGGER, MetadataFormats.METRON_INFO}
)
_FORMATS_WITH_TAGS_WITHOUT_IDS = frozenset(
    {
        MetadataFormats.COMIC_BOOK_INFO,
        MetadataFormats.COMIC_INFO,
        MetadataFormats.COMICTAGGER,
        MetadataFormats.PDF,
        MetadataFormats.PDF_XML,
    }
)
_IDPS_KEYS = frozenset({IDENTIFIERS_KEY, IDENTIFIER_PRIMARY_SOURCE_KEY})


class ComicboxComputedIdentifers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    def _get_computed_from_tags(self, sub_data):
        if (
            not sub_data
            or TAGS_KEY in self._config.delete_keys
            or not self._config.read & _FORMATS_WITH_TAGS_WITHOUT_IDS
        ):
            return None
        tags = sub_data.get(TAGS_KEY)
        if not tags:
            return None
        identifiers = {}
        for tag in tags:
            # Silently fail because most tags are not identifiers
            nid, _, nss = parse_urn_identifier(tag)
            if not (nid and nss):
                nid, _, nss = parse_identifier_other_str(tag)
            if nid:
                nid = ALIAS_NID_MAP.get(nid.lower(), DEFAULT_NID)
                if nss:
                    identifiers[nid] = create_identifier(nid, nss)
        if not identifiers:
            return None
        return {IDENTIFIERS_KEY: identifiers}

    def _get_computed_from_identifiers(self, sub_data):
        if (
            frozenset(self._config.delete_keys) & _IDPS_KEYS
            or not (self._config.write & _FORMATS_WITH_IPS)
            or not sub_data
            or sub_data.get(IDENTIFIER_PRIMARY_SOURCE_KEY)
        ):
            return None
        identifiers = sub_data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return None
        result = None
        for nid in NIDs:
            if nid.value in identifiers and (
                ips := create_identifier_primary_source(nid)
            ):
                result = {IDENTIFIER_PRIMARY_SOURCE_KEY: ips}
                break
        return result

    COMPUTED_ACTIONS = MappingProxyType(
        {
            **ComicboxComputedIssue.COMPUTED_ACTIONS,
            "from tags": (_get_computed_from_tags, AdditiveMerger),
            "from identifiers": (_get_computed_from_identifiers, AdditiveMerger),
        }
    )
