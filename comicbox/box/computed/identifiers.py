"""Comicbox computed identifiers."""

from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.formats import MetadataFormats
from comicbox.identifiers.const import (
    ALIAS_NID_MAP,
    DEFAULT_NID,
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
    IDENTIFIERS_KEY,
    TAGS_KEY,
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


class ComicboxComputedIdentifers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    @staticmethod
    def _add_identifier_from_tag(tag: str, identifiers: dict):
        # Silently fail because most tags are not identifiers
        nid, _, nss = parse_urn_identifier(tag)
        if not (nid and nss):
            nid, _, nss = parse_identifier_other_str(tag)
        if nid:
            nid = ALIAS_NID_MAP.get(nid.lower(), DEFAULT_NID)
            if nss:
                identifiers[nid] = create_identifier(nid, nss)

    def _get_computed_from_tags(self, sub_data):
        # only look for ids in tags if the format has tags but no designated id field.
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
            self._add_identifier_from_tag(tag, identifiers)
        if not identifiers:
            return None
        return {IDENTIFIERS_KEY: identifiers}

    COMPUTED_ACTIONS = MappingProxyType(
        {
            **ComicboxComputedIssue.COMPUTED_ACTIONS,
            "from tags": (_get_computed_from_tags, AdditiveMerger),
        }
    )
