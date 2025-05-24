"""Comicbox computed identifiers."""

from collections.abc import Callable
from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_SOURCE,
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
from comicbox.merge import AdditiveMerger, Merger
from comicbox.schemas.comicbox import (
    IDENTIFIERS_KEY,
    TAGS_KEY,
)


class ComicboxComputedIdentifiers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    @staticmethod
    def _add_identifier_from_tag(tag: str, identifiers: dict):
        # Silently fail because most tags are not identifiers
        id_source, _, id_key = parse_urn_identifier(tag)
        if not (id_source and id_key):
            id_source, _, id_key = parse_identifier_other_str(tag)
        if id_source:
            id_source = ALIAS_ID_SOURCE_MAP.get(id_source.lower(), DEFAULT_ID_SOURCE)
            if id_key:
                identifiers[id_source] = create_identifier(id_source, id_key)

    def _get_computed_from_tags(self, sub_data):
        # only look for ids in tags if the format has tags but no designated id field.
        if (
            not sub_data
            or self._config.computed.is_skip_computed_from_tags
            or TAGS_KEY in self._config.delete_keys
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

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                **ComicboxComputedIssue.COMPUTED_ACTIONS,
                "from tags": (_get_computed_from_tags, AdditiveMerger),
            }
        )
    )
