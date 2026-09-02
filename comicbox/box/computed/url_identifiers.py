"""
Collect web urls and the ids they contain.

Two actions at the head of the computed pipeline, in this order.

Urls hide in the notes field, because most formats have nowhere else to put
one and taggers write them into their notes text. A url there is still a
url, so it is collected into the urls list before anything else looks at it.
That also saves it: the tagger stamp rewrites notes, and a url that lived
only in the prose it replaces would be gone.

Then the ids are read out of every url, before the weaker places an id can
hide. A url naming a database's own id path states that id more plainly
than notes prose or a tag does, so it is filled in first and those sources
only fill what it left. An id the file states outright still beats all of
them.

The other direction, synthesizing a url for an identifier that lacks one,
runs at the far end of the pipeline in ``urls``.
"""

import re
from typing import Any

from comicbox.box.merge import ComicboxMerge
from comicbox.formats.base.transforms.identifiers import identifier_from_url
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    NOTES_KEY,
    URLS_KEY,
)
from comicbox.identifiers.identifiers import get_url_from_identifier

_NOTES_URL_RE = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
# Notes are sentences. A url at the end of one takes the punctuation with it,
# and a bracketed or parenthesized url takes the closing mark.
_URL_TRAILING_CHARS = ".,;:!?)]}>'\""


class ComicboxComputedUrlIdentifiers(ComicboxMerge):
    """Collect urls written into notes and the ids that urls contain."""

    def _get_computed_urls_from_notes(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, list] | None:
        """Collect the web urls a tagger wrote into the notes text."""
        if not sub_data:
            return None
        notes = sub_data.get(NOTES_KEY)
        if not notes:
            return None
        old_urls = frozenset(str(url) for url in sub_data.get(URLS_KEY) or ())
        new_urls: dict[str, None] = {}
        for match in _NOTES_URL_RE.finditer(notes):
            url = match.group().rstrip(_URL_TRAILING_CHARS)
            if url and url not in old_urls:
                new_urls[url] = None
        if not new_urls:
            return None
        return {URLS_KEY: list(new_urls)}

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
        return get_url_from_identifier(id_source_str, identifier) == url

    @classmethod
    def _add_identifier_from_url(
        cls,
        url: str,
        old_identifiers: dict[str, Any],
        new_identifiers: dict[str, dict],
    ) -> None:
        """Record the id one url names, if it beats what the url list holds."""
        id_source_str, identifier = identifier_from_url(url)
        # An explicit id always wins. For several databases the url path
        # is a slug, not the id, so it must not overwrite a real key.
        if not (id_source_str and identifier) or id_source_str in old_identifiers:
            return
        if id_source_str not in new_identifiers or cls._url_holds_its_key(
            id_source_str, identifier, url
        ):
            new_identifiers[id_source_str] = identifier

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
            self._add_identifier_from_url(str(url), old_identifiers, new_identifiers)
        if not new_identifiers:
            return None
        return {IDENTIFIERS_KEY: new_identifiers}
