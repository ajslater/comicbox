"""Comicbox computed identifiers."""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from comicbox.box.computed.issue import ComicboxComputedIssue
from comicbox.formats.comicbox.schema import (
    ARCS_KEY,
    CHARACTERS_KEY,
    CREDITS_KEY,
    GENRES_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    LOCATIONS_KEY,
    PUBLISHER_KEY,
    ROLES_KEY,
    SERIES_KEY,
    STORIES_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
)
from comicbox.identifiers import ID_KEY_KEY
from comicbox.identifiers.identifiers import (
    create_identifier,
    normalize_key,
)
from comicbox.identifiers.other import (
    parse_identifier_other_str,
)
from comicbox.identifiers.urns import (
    parse_urn_identifier,
)
from comicbox.merge import AdditiveMerger, Merger

_IDENTIFIED_KEYS = (PUBLISHER_KEY, IMPRINT_KEY, SERIES_KEY)
_IDENTIFIED_TAG_KEYS = (
    ARCS_KEY,
    CHARACTERS_KEY,
    CREDITS_KEY,
    GENRES_KEY,
    LOCATIONS_KEY,
    STORIES_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
)
_IRREGULAR_SINGULAR_ID_TYPES = MappingProxyType(
    {
        CREDITS_KEY: "creator",
        STORIES_KEY: "story",
    }
)
_PARSE_AS_IDENTIFIERS = frozenset({TAGS_KEY, GENRES_KEY})


class ComicboxComputedIdentifiers(ComicboxComputedIssue):
    """Comicbox computed identifiers."""

    @staticmethod
    def _add_identifier_from_tag(tag: str, identifiers: dict) -> None:
        # Silently fail because most tags are not identifiers
        id_source, id_type, id_key = parse_urn_identifier(tag)
        if not (id_source and id_key):
            id_source, id_type, id_key = parse_identifier_other_str(tag)
        if id_source and id_key:
            identifiers[id_source.value] = create_identifier(
                id_source.value, id_key, id_type=id_type
            )

    def _get_computed_from_tags(
        self, sub_data: dict[str, Any]
    ) -> dict[str, dict] | None:
        # only look for ids in tags and genres if the format has tags but no designated id field.
        if (
            not sub_data
            or self._config.is_skip_computed_from_tags
            or _PARSE_AS_IDENTIFIERS.issubset(self._config.general.delete_keys)
        ):
            return None
        identifiers = {}
        for key in _PARSE_AS_IDENTIFIERS:
            if tags := sub_data.get(key):
                for tag in tags:
                    self._add_identifier_from_tag(tag, identifiers)

        if not identifiers:
            return None
        return {IDENTIFIERS_KEY: identifiers}

    @staticmethod
    def _key_deltas_for_tag_identifiers(
        id_type: str, identifiers: Mapping | None
    ) -> dict[str, dict[str, str]]:
        """
        Clean hand-tagged identifier keys for one identifiers map.

        Returns ``{source: {"key": ...}}`` deltas instead of writing into the
        input: computed actions must not mutate the merged metadata they
        derive from (it's cached); the action's return value is merged by its
        declared merger like every other action.

        Hand-tagged keys often mirror the urn form comicbox writes to notes,
        carrying a type prefix ("series:178012") or a comicvine long code.
        Keys read through a format transform were cleaned on the way in; these
        are the ones written by hand.
        """
        deltas: dict[str, dict[str, str]] = {}
        if not identifiers:
            return deltas
        for id_source_str, identifier in identifiers.items():
            if not (id_key := identifier.get(ID_KEY_KEY)):
                continue
            _, norm_id_key = normalize_key(id_source_str, id_type, id_key)
            if norm_id_key != id_key:
                deltas[id_source_str] = {ID_KEY_KEY: norm_id_key}
        return deltas

    @classmethod
    def _key_deltas_for_tag(cls, id_type: str, tag: Mapping | None) -> dict | None:
        """Delta subtree for one identified tag, or None when clean."""
        if not tag:
            return None
        deltas = cls._key_deltas_for_tag_identifiers(id_type, tag.get(IDENTIFIERS_KEY))
        return {IDENTIFIERS_KEY: deltas} if deltas else None

    @classmethod
    def _key_deltas_for_multiple_tags(cls, key: str, all_tags: Mapping) -> dict:
        """Delta subtrees for a name-keyed tag map (credits incl. roles)."""
        id_type = _IRREGULAR_SINGULAR_ID_TYPES.get(key, key[:-1])
        tag_deltas: dict[str, Any] = {}
        for name, tag in all_tags.items():
            delta = cls._key_deltas_for_tag(id_type, tag) or {}
            if key == CREDITS_KEY and tag and (roles := tag.get(ROLES_KEY)):
                role_deltas = {
                    role_name: role_delta
                    for role_name, role in roles.items()
                    if (role_delta := cls._key_deltas_for_tag(id_type, role))
                }
                if role_deltas:
                    delta = {**delta, ROLES_KEY: role_deltas}
            if delta:
                tag_deltas[name] = delta
        return tag_deltas

    def _normalize_all_identifier_keys(self, sub_data: dict[str, Any]) -> dict | None:
        """Clean hand-tagged identifier keys as a mergeable delta tree."""
        tree: dict[str, Any] = {}
        if deltas := self._key_deltas_for_tag_identifiers(
            "issue", sub_data.get(IDENTIFIERS_KEY)
        ):
            tree[IDENTIFIERS_KEY] = deltas
        for key in _IDENTIFIED_KEYS:
            if delta := self._key_deltas_for_tag(key, sub_data.get(key)):
                tree[key] = delta
        for key in _IDENTIFIED_TAG_KEYS:
            all_tags = sub_data.get(key)
            if not all_tags:
                continue
            if tag_deltas := self._key_deltas_for_multiple_tags(key, all_tags):
                tree[key] = tag_deltas
        return tree or None

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                **ComicboxComputedIssue.COMPUTED_ACTIONS,
                "from tags": (_get_computed_from_tags, AdditiveMerger),
                "normalize identifier keys": (
                    _normalize_all_identifier_keys,
                    AdditiveMerger,
                ),
            }
        )
    )
