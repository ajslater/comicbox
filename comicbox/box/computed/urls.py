"""
Synthesize a url for every identifier that lacks one.

Comicbox stores identifier keys and web urls separately, the way MetronInfo
does, but a reader given only one of them still wants the other. This runs
after every source of identifiers has been consulted and their keys
normalized, and before the tagger stamp bakes the urns into notes, so a
comic tagged with nothing but a url still gets a complete stamp.

Reading ids out of urls, the other direction, runs at the head of the
pipeline in ``url_identifiers``.
"""

from typing import Any

from comicbox.box.computed.identifiers import ComicboxComputedIdentifiers
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    URLS_KEY,
)
from comicbox.identifiers.identifiers import get_url_from_identifier


class ComicboxComputedUrls(ComicboxComputedIdentifiers):
    """Fill urls from identifiers."""

    def _get_computed_urls(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, list] | None:
        """
        Synthesize a url for every identifier that lacks one, and dedupe.

        Merging several sources that each name the same url appends it once
        per source, because the merger extends lists. The result replaces
        the list rather than extending it, so it is deduped here too.
        """
        if not sub_data:
            return None
        old_urls = sub_data.get(URLS_KEY) or ()
        # dict keys keep insertion order, so the file's own urls stay first.
        urls: dict[str, None] = dict.fromkeys(str(url) for url in old_urls)
        for id_source_str, identifier in (sub_data.get(IDENTIFIERS_KEY) or {}).items():
            if url := get_url_from_identifier(id_source_str, identifier):
                urls.setdefault(url, None)
        url_list = list(urls)
        if not url_list or url_list == list(old_urls):
            return None
        return {URLS_KEY: url_list}
