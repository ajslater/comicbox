"""Pages methods."""

from comicbox.box.archive.filenames import ComicboxArchiveFilenames
from comicbox.box.archive.init import archive_close


class ComicboxArchivePages(ComicboxArchiveFilenames):
    """Pages methods."""

    @archive_close
    def get_page_by_filename(self, filename: str, *, to_pixmap: bool = False):
        """Return data for a single page by filename."""
        return self._archive_readfile(filename, to_pixmap=to_pixmap)

    @archive_close
    def get_pages(self, page_from=0, page_to=-1, *, to_pixmap: bool = False):
        """Generate all pages starting with page number."""
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in pagenames:
                yield self._archive_readfile(pagename, to_pixmap=to_pixmap)

    @archive_close
    def get_page_by_index(self, index: int, *, to_pixmap: bool = False):
        """Get the page data by index."""
        if pages_generator := self.get_pages(
            page_from=index, page_to=index, to_pixmap=to_pixmap
        ):
            return next(pages_generator)
        return None
