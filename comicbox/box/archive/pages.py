"""Pages methods."""

from collections.abc import Iterator

from comicbox.box.archive.filenames import ComicboxArchiveFilenames


class ComicboxArchivePages(ComicboxArchiveFilenames):
    """Pages methods."""

    def get_page_by_filename(self, filename: str, pdf_format: str = "") -> bytes:
        """Return data for a single page by filename."""
        return self._archive_readfile(filename, pdf_format=pdf_format)

    def get_pages(
        self, page_from: int = 0, page_to: int | None = None, pdf_format: str = ""
    ) -> Iterator:
        """
        Generate the pages from ``page_from`` to ``page_to``, inclusive.

        A ``page_to`` of None, or below 0, is the last page. A ``page_from``
        below 0 counts back from the last page, as a slice does: -1 is the
        last page. A range partly past the last page reads the pages it
        covers; one that matches no page reads nothing. A 7z is
        decompressed in batches, as a conversion reads it: read one at a
        time, each page re-decoded its solid block from the start.
        """
        if page_to is not None and page_to < 0:
            page_to = None
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in self._iter_prefetched(pagenames):
                yield self._archive_readfile(pagename, pdf_format=pdf_format)

    def get_page_by_index(self, index: int, pdf_format: str = "") -> bytes | None:
        """Get the page data by index."""
        if pagename := self.get_pagename(index):
            return self.get_page_by_filename(pagename, pdf_format=pdf_format)
        return None
