"""Pages methods."""

from logging import getLogger

from comicbox.box.archive.read import archive_close
from comicbox.box.pages.covers import ComicboxPagesCoversMixin

LOG = getLogger(__name__)


class ComicboxPagesMixin(ComicboxPagesCoversMixin):
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

    def _get_cover_page(self, *, to_pixmap: bool = False):
        data = None
        cover_paths = self.generate_cover_paths()
        bad_cover_paths = set()
        for cover_path in cover_paths:
            if cover_path in bad_cover_paths:
                continue
            try:
                data = self._archive_readfile(cover_path, to_pixmap=to_pixmap)
                break
            except Exception as exc:
                LOG.warning(f"{self._path} reading cover: {cover_path}: {exc}")
                bad_cover_paths.add(cover_path)
        return data

    @archive_close
    def get_cover_page(self, *, to_pixmap: bool = False):
        """Return cover image data."""
        return self._get_cover_page(to_pixmap=to_pixmap)
