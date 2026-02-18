"""Pages methods."""

from collections.abc import Iterator

from comicbox.box.archive.filenames import ComicboxArchiveFilenames


class ComicboxArchivePages(ComicboxArchiveFilenames):
    """Pages methods."""

    def get_page_by_filename(self, filename: str, pdf_format: str = "") -> bytes:
        """Return data for a single page by filename."""
        return self._archive_readfile(filename, pdf_format=pdf_format)

    def get_pages(self, page_from=0, page_to=-1, pdf_format: str = "") -> Iterator:
        """Generate all pages starting with page number."""
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in pagenames:
                yield self._archive_readfile(pagename, pdf_format=pdf_format)

    def get_page_by_index(self, index: int, pdf_format: str = "") -> bytes | None:
        """Get the page data by index."""
        if pages_generator := self.get_pages(
            page_from=index, page_to=index, pdf_format=pdf_format
        ):
            return next(pages_generator)
        return None
