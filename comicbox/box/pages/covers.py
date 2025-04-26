"""Cover Page filename methods."""

from collections.abc import Generator
from logging import getLogger

from glom import glom

from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.box.pages.filenames import ComicboxPageFilenamesMixin
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox import COVER_IMAGE_KEY, PAGES_KEY, ComicboxSchemaMixin

PAGES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGES_KEY}"
_COVER_IMAGE_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{COVER_IMAGE_KEY}"
LOG = getLogger(__name__)


class ComicboxPagesCoversMixin(ComicboxMetadataMixin, ComicboxPageFilenamesMixin):
    """Cover path methods."""

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
        if cover_image := glom(metadata, _COVER_IMAGE_KEYPATH, default=None):
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
