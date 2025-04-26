"""Pages methods."""

from logging import getLogger

from comicbox.box.archive.read import archive_close
from comicbox.box.pages.covers import ComicboxPagesCoversMixin

LOG = getLogger(__name__)


class ComicboxPagesMixin(ComicboxPagesCoversMixin):
    """Pages methods."""

    @archive_close
    def get_page_by_filename_pdf_to_pixmap(self, filename: str):
        """Return data for a single pdf page by filename to a pixmap."""
        return self._archive_readfile_pdf_to_pixmap(filename)

    @archive_close
    def get_page_by_filename(self, filename: str):
        """Return data for a single page by filename."""
        return self._archive_readfile(filename)

    @archive_close
    def get_pages_pdf_to_pixmap(
        self,
        page_from=0,
        page_to=-1,
    ):
        """Generate all pages starting with page number."""
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in pagenames:
                yield self._archive_readfile_pdf_to_pixmap(pagename)

    @archive_close
    def get_pages(self, page_from=0, page_to=-1):
        """Generate all pages starting with page number."""
        if pagenames := self.get_pagenames_from(page_from, page_to):
            for pagename in pagenames:
                yield self._archive_readfile(pagename)

    @archive_close
    def get_page_by_index_pdf_to_pixmap(self, index: int):
        """Get the page data by index."""
        if pages_generator := self.get_pages_pdf_to_pixmap(
            page_from=index,
            page_to=index,
        ):
            return next(pages_generator)
        return None

    @archive_close
    def get_page_by_index(self, index: int):
        """Get the page data by index."""
        if pages_generator := self.get_pages(page_from=index, page_to=index):
            return next(pages_generator)
        return None

    def _get_cover_page(self, readfile_func):
        data = None
        cover_paths = self.generate_cover_paths()
        bad_cover_paths = set()
        for cover_path in cover_paths:
            if cover_path in bad_cover_paths:
                continue
            try:
                data = readfile_func(cover_path)
                break
            except Exception as exc:
                LOG.warning(f"{self._path} reading cover: {cover_path}: {exc}")
                bad_cover_paths.add(cover_path)
        return data

    @archive_close
    def get_cover_page_pdf_to_pixmap(self):
        """Return cover image from a pdf to a pixmap."""
        return self._get_cover_page(self._archive_readfile_pdf_to_pixmap)

    @archive_close
    def get_cover_page(self):
        """Return cover image data."""
        return self._get_cover_page(self._archive_readfile)
