"""Cover methods."""

from logging import getLogger

from comicbox.box.archive_read import archive_close
from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox import PAGES_KEY

LOG = getLogger(__name__)


class ComicboxPagesMixin(ComicboxMetadataMixin):
    """Cover methods."""

    ########################
    # COVER PATH FILENAMES #
    ########################

    def _get_cover_page_filenames_tagged(self):
        """Overridden by CIX."""
        coverlist = []
        metadata = self._get_metadata()
        if not metadata:
            return coverlist

        # Support zero and one index pages.
        has_zero_index = False
        for page in metadata.get(PAGES_KEY, []):
            index = page.get("index")
            if index == 0:
                has_zero_index = True
            if page.get("page_type") == PageTypeEnum.FRONT_COVER:
                if not has_zero_index:
                    index = max(index - 1, 0)
                if pagename := self.get_pagename(index):
                    coverlist.append(pagename)
        return coverlist

    def get_cover_path_list(self):
        """Get filename of most likely coverpage."""
        if not self._cover_path_list:
            cover_path_list = []
            cover_path_list += self._get_cover_page_filenames_tagged()
            metadata = self._get_metadata()
            if md_cover_image := metadata.get("cover_image"):
                pagenames = self.get_page_filenames()
                if md_cover_image in pagenames:
                    cover_path_list.append(md_cover_image)
            if first_pagename := self.get_pagename(0):
                cover_path_list.append(first_pagename)
            if not cover_path_list:
                LOG.warning(f"{self._path} could not find cover filename")
            self._cover_path_list = tuple(frozenset(cover_path_list))
        return self._cover_path_list

    #############
    # PAGE DATA #
    #############
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

    @archive_close
    def get_cover_page_pdf_to_pixmap(self):
        """Return cover image from a pdf to a pixmap."""
        data = None
        cover_path_list = self.get_cover_path_list()
        for cover_fn in cover_path_list:
            try:
                data = self._archive_readfile_pdf_to_pixmap(cover_fn)
                break
            except Exception as exc:
                LOG.warning(f"{self._path} reading cover: {cover_fn}: {exc}")
        return data

    @archive_close
    def get_cover_page(self):
        """Return cover image data."""
        data = None
        cover_path_list = self.get_cover_path_list()
        for cover_fn in cover_path_list:
            try:
                data = self._archive_readfile(cover_fn)
                break
            except Exception as exc:
                LOG.warning(f"{self._path} reading cover: {cover_fn}: {exc}")
        return data
