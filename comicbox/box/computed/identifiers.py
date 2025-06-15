"""Comicbox computed identifiers."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_SOURCE,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
    get_identifier_url,
)
from comicbox.identifiers.other import (
    parse_identifier_other_str,
)
from comicbox.identifiers.urns import (
    parse_urn_identifier,
)
from comicbox.merge import AdditiveMerger, Merger
from comicbox.schemas.comicbox import (
    ARCS_KEY,
    CHARACTERS_KEY,
    CREDITS_KEY,
    GENRES_KEY,
    ID_KEY_KEY,
    ID_URL_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    LOCATIONS_KEY,
    PUBLISHER_KEY,
    ROLES_KEY,
    SERIES_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
)

_IDENTIFIED_KEYS = (PUBLISHER_KEY, IMPRINT_KEY, SERIES_KEY)
_IDENTIFIED_TAG_KEYS = (
    ARCS_KEY,
    CHARACTERS_KEY,
    CREDITS_KEY,
    GENRES_KEY,
    LOCATIONS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
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

    @staticmethod
    def _add_url_to_tag_identifiers(id_type: str, identifiers: Mapping | None):
        all_urls = []
        if not identifiers:
            return all_urls
        for id_source, identifier in identifiers.items():
            if identifier.get(ID_URL_KEY):
                continue
            if (id_key := identifier.get(ID_KEY_KEY)) and (
                url := get_identifier_url(id_source, id_type, id_key)
            ):
                identifier[ID_URL_KEY] = url
                all_urls.append(url)
        return all_urls

    @classmethod
    def _add_urls_to_identifiers(cls, sub_data, all_urls):
        identifiers = sub_data.get(IDENTIFIERS_KEY)
        if urls := cls._add_url_to_tag_identifiers("issue", identifiers):
            all_urls[IDENTIFIERS_KEY] = urls

    @classmethod
    def _add_urls_to_tag(cls, key: str, id_type: str, tag: dict, all_urls: dict):
        if not tag:
            return
        identifiers = tag.get(IDENTIFIERS_KEY)
        if urls := cls._add_url_to_tag_identifiers(
            id_type,
            identifiers,
        ):
            if key not in all_urls:
                all_urls[key] = []
            all_urls[key].extend(urls)

    @classmethod
    def _add_urls_to_single_tags(cls, sub_data, all_urls):
        for key in _IDENTIFIED_KEYS:
            tag = sub_data.get(key)
            cls._add_urls_to_tag(key, key, tag, all_urls)

    @classmethod
    def _add_urls_to_multiple_tags(cls, sub_data, all_urls):
        for key in _IDENTIFIED_TAG_KEYS:
            all_tags = sub_data.get(key)
            if not all_tags:
                continue
            id_type = "creator" if key == CREDITS_KEY else key[:-1]
            for tag in all_tags.values():
                cls._add_urls_to_tag(key, id_type, tag, all_urls)
                if key == CREDITS_KEY and (roles := tag.get(ROLES_KEY)):
                    for role in roles.values():
                        cls._add_urls_to_tag(ROLES_KEY, id_type, role, all_urls)

    def _add_urls_to_all_identifiers(self, sub_data):
        """Add missing urls to identifiers."""
        all_urls = {}
        self._add_urls_to_identifiers(sub_data, all_urls)
        self._add_urls_to_single_tags(sub_data, all_urls)
        self._add_urls_to_multiple_tags(sub_data, all_urls)

        if not all_urls:
            return None
        return all_urls

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                **ComicboxComputedIssue.COMPUTED_ACTIONS,
                "from tags": (_get_computed_from_tags, AdditiveMerger),
                "add urls to identifiers": (_add_urls_to_all_identifiers, None),
            }
        )
    )
