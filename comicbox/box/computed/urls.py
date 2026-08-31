"""
Derive identifiers and urls from each other.

Comicbox stores identifier keys and web urls separately, the way MetronInfo
does, but a reader given only one of them still wants the other. These
actions fill each side's gaps from the other without either becoming stored
source data that could contradict the file.

They run before the tagger stamp, which bakes identifier urns into the notes
field, so a comic tagged with nothing but a url still gets a complete stamp.
Computed actions all read one shared snapshot, so filling identifiers updates
that snapshot in place; the returned delta is merged like any other action's.
"""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from comicbox.box.computed.notes import ComicboxComputedNotes
from comicbox.formats.base.transforms.identifiers import identifier_from_url
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    URLS_KEY,
)
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_KEY_KEY, ID_TYPE_KEY
from comicbox.identifiers.identifiers import get_identifier_url
from comicbox.merge import AdditiveMerger, Merger


class ComicboxComputedUrls(ComicboxComputedNotes):
    """Fill identifiers from urls and urls from identifiers."""

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
        # Update the shared snapshot so the notes stamp sees these too.
        sub_data.setdefault(IDENTIFIERS_KEY, {}).update(new_identifiers)
        return {IDENTIFIERS_KEY: new_identifiers}

    def _get_computed_urls_from_identifiers(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, list] | None:
        """Synthesize a web url for every identifier that lacks one."""
        identifiers = sub_data.get(IDENTIFIERS_KEY) if sub_data else None
        if not identifiers:
            return None
        old_urls = [str(url) for url in sub_data.get(URLS_KEY) or ()]
        new_urls = []
        for id_source_str, identifier in identifiers.items():
            id_key = identifier.get(ID_KEY_KEY) if identifier else None
            if not id_key:
                continue
            id_type = identifier.get(ID_TYPE_KEY) or DEFAULT_ID_TYPE
            url = get_identifier_url(id_source_str, id_type, id_key)
            if url and url not in old_urls and url not in new_urls:
                new_urls.append(url)
        if not new_urls:
            return None
        # Only the new ones: the additive merger extends the existing list.
        return {URLS_KEY: new_urls}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                **ComicboxComputedNotes.COMPUTED_ACTIONS,
                "identifiers from urls": (
                    _get_computed_identifiers_from_urls,
                    AdditiveMerger,
                ),
                "urls from identifiers": (
                    _get_computed_urls_from_identifiers,
                    AdditiveMerger,
                ),
            }
        )
    )
