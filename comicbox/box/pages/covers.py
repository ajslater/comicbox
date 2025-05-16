"""Cover Page filename methods."""

from collections.abc import Generator

from glom import glom
from loguru import logger

from comicbox.box.archive import archive_close
from comicbox.box.metadata import ComicboxMetadata
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox import COVER_IMAGE_KEY, PAGES_KEY, ComicboxSchemaMixin

PAGES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGES_KEY}"
_COVER_IMAGE_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{COVER_IMAGE_KEY}"


class ComicboxPagesCovers(ComicboxMetadata):
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

    def _get_cover_paths(self) -> tuple[str, ...]:
        cover_path_generator = self.generate_cover_paths()
        cover_paths_ordered_set = dict.fromkeys(cover_path_generator)
        cover_paths = tuple(cover_paths_ordered_set.keys())
        if not cover_paths:
            logger.warning(f"{self._path} could not find cover filename")
        return cover_paths

    def get_cover_paths(self):
        """Get filename of most likely coverpage."""
        # This could be a generator?
        if self._cover_paths is None:
            self._cover_paths: tuple[str, ...] | None = self._get_cover_paths()
        return self._cover_paths

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
                logger.warning(f"{self._path} reading cover: {cover_path}: {exc}")
                bad_cover_paths.add(cover_path)
        return data

    @archive_close
    def get_cover_page(self, *, to_pixmap: bool = False):
        """Return cover image data."""
        return self._get_cover_page(to_pixmap=to_pixmap)
