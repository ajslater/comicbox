"""
Read the ids that database urls contain.

This runs before the weaker places an id can hide. A url naming a database's
own id path states that id more plainly than notes text or a tag does, so it
is filled in first and those sources only fill what it left. An id the file
states outright still beats all of them.

The other direction, synthesizing a url for an identifier that lacks one,
runs at the far end of the pipeline in ``urls``, once every source of
identifiers has been consulted and their keys normalized.
"""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from comicbox.box.merge import ComicboxMerge
from comicbox.formats.base.transforms.identifiers import identifier_from_url
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    URLS_KEY,
)
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_KEY_KEY, ID_TYPE_KEY
from comicbox.identifiers.identifiers import get_identifier_url
from comicbox.merge import AdditiveMerger, Merger


class ComicboxComputedUrlIdentifiers(ComicboxMerge):
    """Fill identifiers from the urls that contain them."""

    @staticmethod
    def _url_holds_its_key(
        id_source_str: str, identifier: dict[str, str], url: str
    ) -> bool:
        """
        Say whether a url contains its database's id rather than a slug.

        A url that rebuilds itself from the key it parsed to is the canonical
        form for that key. When a comic carries both a slug url and a
        canonical one for the same database, the canonical one names the id.
        """
        id_key = identifier.get(ID_KEY_KEY)
        if not id_key:
            return False
        id_type = identifier.get(ID_TYPE_KEY) or DEFAULT_ID_TYPE
        return get_identifier_url(id_source_str, id_type, id_key) == url

    def _get_computed_identifiers_from_urls(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, dict] | None:
        """Recognize database urls and record the ids they contain."""
        urls = sub_data.get(URLS_KEY) if sub_data else None
        if not urls:
            return None
        old_identifiers = sub_data.get(IDENTIFIERS_KEY) or {}
        new_identifiers: dict[str, dict] = {}
        for url in urls:
            id_source_str, identifier = identifier_from_url(str(url))
            # An explicit id always wins. For several databases the url path
            # is a slug, not the id, so it must not overwrite a real key.
            if not (id_source_str and identifier) or id_source_str in old_identifiers:
                continue
            if id_source_str not in new_identifiers or self._url_holds_its_key(
                id_source_str, identifier, str(url)
            ):
                new_identifiers[id_source_str] = identifier
        if not new_identifiers:
            return None
        return {IDENTIFIERS_KEY: new_identifiers}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                "identifiers from urls": (
                    _get_computed_identifiers_from_urls,
                    AdditiveMerger,
                ),
            }
        )
    )
