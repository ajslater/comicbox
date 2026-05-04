"""Cover Page filename methods."""

from collections.abc import Generator

from glom import glom
from loguru import logger

from comicbox.box.metadata import ComicboxMetadata
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.schemas.comicbox import COVER_IMAGE_KEY, PAGES_KEY, ComicboxSchemaMixin

PAGES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGES_KEY}"
_COVER_IMAGE_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{COVER_IMAGE_KEY}"


class ComicboxPagesCovers(ComicboxMetadata):
    """Cover path methods."""

    def _generate_cover_paths_from_pages(self, pages: dict) -> Generator[str]:
        """Overridden by CIX."""
        # Support zero and one index pages.
        has_zero_index = 0 in pages
        for index, page in pages.items():
            if page.get("page_type") != ComicInfoPageTypeEnum.FRONT_COVER:
                continue
            pagename_index = index if has_zero_index else max(index - 1, 0)
            if pagename := self.get_pagename(pagename_index):
                yield pagename

    def generate_cover_paths(self) -> Generator[str]:
        """Generate cover paths."""
        metadata = dict(self.get_internal_metadata())
        if pages := glom(metadata, PAGES_KEYPATH, default=None):
            yield from self._generate_cover_paths_from_pages(pages)
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

    def get_cover_paths(self) -> tuple[str, str, str]:
        """Get filename of most likely coverpage."""
        # This could be a generator?
        if self._cover_paths is None:
            self._cover_paths = self._get_cover_paths()
        return self._cover_paths  # pyright: ignore[reportReturnType], #ty: ignore[invalid-return-type]

    def _get_cover_page_skip_metadata(self, pdf_format: str = "") -> bytes:
        first_pagename = self.get_pagename(0)
        if not first_pagename:
            return b""
        try:
            return self._archive_readfile(first_pagename, pdf_format=pdf_format)
        except Exception as exc:
            logger.warning(f"{self._path} reading first page: {first_pagename}: {exc}")
            return b""

    def _get_cover_page(
        self, pdf_format: str = "", *, skip_metadata: bool = False
    ) -> bytes:
        if skip_metadata:
            return self._get_cover_page_skip_metadata(pdf_format=pdf_format)
        data = b""
        cover_paths = self.generate_cover_paths()
        bad_cover_paths = set()
        for cover_path in cover_paths:
            if cover_path in bad_cover_paths:
                continue
            try:
                data = self._archive_readfile(cover_path, pdf_format=pdf_format)
                break
            except Exception as exc:
                logger.warning(f"{self._path} reading cover: {cover_path}: {exc}")
                bad_cover_paths.add(cover_path)
        return data

    def get_cover_page(
        self, pdf_format: str = "", *, skip_metadata: bool = False
    ) -> bytes:
        """
        Return cover image data.

        When skip_metadata is True, bypass cover-hint metadata parsing and
        return the bytes of the first archive page directly. Useful for
        callers that only need a thumbnail and want to avoid the cost of
        schema instantiation and Union resolution.
        """
        return self._get_cover_page(pdf_format=pdf_format, skip_metadata=skip_metadata)
