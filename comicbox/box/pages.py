"""Cover methods."""

from collections.abc import Generator
from logging import getLogger

from glom import glom

from comicbox.box.archive_read import archive_close
from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox import COVER_IMAGE_KEY, PAGES_KEY, ComicboxSchemaMixin

PAGES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGES_KEY}"
COVER_IMAGE_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{COVER_IMAGE_KEY}"
LOG = getLogger(__name__)


class ComicboxPagesMixin(ComicboxMetadataMixin):
    """Cover methods."""

    ########################
    # COVER PATH FILENAMES #
    ########################

    def _generate_cover_paths_from_pages(self, metadata: dict) -> Generator[str]:
        """Overridden by CIX."""
        if not metadata:
            return
        metadata = dict(metadata)
        pages = glom(metadata, PAGES_KEYPATH, default=None)
        if not pages:
            return

        # Support zero and one index pages.
        has_zero_index = 0 in pages
        for index, page in pages.items():
            if page.get("page_type") != PageTypeEnum.FRONT_COVER:
                continue
            pagename_index = index if has_zero_index else max(index - 1, 0)
            if pagename := self.get_pagename(pagename_index):
                yield pagename

    def generate_cover_paths(self) -> Generator[str]:
        """Generate cover paths."""
        metadata = self._get_metadata()
        metadata = dict(metadata)
        yield from self._generate_cover_paths_from_pages(metadata)
        if cover_image := glom(metadata, COVER_IMAGE_KEYPATH, default=None):
            pagenames = self.get_page_filenames()
            if cover_image in pagenames:
                yield cover_image
        if first_pagename := self.get_pagename(0):
            yield first_pagename

    def _get_cover_paths(self):
        cover_path_generator = self.generate_cover_paths()
        cover_paths_ordered_set = dict.fromkeys(cover_path_generator)
        cover_paths = tuple(cover_paths_ordered_set.keys())
        if not cover_paths:
            LOG.warning(f"{self._path} could not find cover filename")
        return cover_paths

    def get_cover_paths(self):
        """Get filename of most likely coverpage."""
        # This could be a generator?
        if not self._cover_paths:
            self._cover_paths = self._get_cover_paths()
        return self._cover_paths

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
