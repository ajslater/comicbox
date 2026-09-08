"""Comicbox Computed Pages."""

from collections.abc import Mapping, MutableMapping
from sys import maxsize
from types import MappingProxyType
from typing import Any

from loguru import logger

from comicbox.box.computed.urls import ComicboxComputedUrls
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.formats.comicbox.schema import (
    BOOKMARK_KEY,
    PAGE_BOOKMARK_KEY,
    PAGE_COUNT_KEY,
    PAGE_SIZE_KEY,
    PAGE_TYPE_KEY,
    PAGES_KEY,
)
from comicbox.merge import AdditiveMerger

_ENABLE_PAGE_COMPUTE_ATTRS = MappingProxyType(
    {
        PAGE_COUNT_KEY: ("page_count", "HAS_PAGE_COUNT"),
        PAGES_KEY: ("pages", "HAS_PAGES"),
    }
)


class ComicboxComputedPages(ComicboxComputedUrls):
    """Comicbox Computed Pages."""

    def _enable_page_compute_attribute(self, key: str, sub_md: Mapping) -> bool:
        """Determine if we should compute this attribute."""
        if key in self._config.general.delete_keys or not sub_md or not self._path:
            return False
        formats = frozenset(self._config.all_write_formats | self._dict_formats)
        compute_attr, schema_attr = _ENABLE_PAGE_COMPUTE_ATTRS[key]
        return getattr(self._config.compute, compute_attr, False) and (
            any(getattr(fmt.value.schema_class, schema_attr, False) for fmt in formats)
        )

    def _get_computed_page_count_metadata(
        self, sub_md: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Compute page_count from page_filenames.

        Allow for extra images in the archive that are not pages.
        """
        if not self._enable_page_compute_attribute(PAGE_COUNT_KEY, sub_md):
            return None
        md_page_count = sub_md.get(PAGE_COUNT_KEY)
        real_page_count = self.get_page_count()
        if md_page_count != real_page_count:
            return {PAGE_COUNT_KEY: real_page_count}
        return None

    @staticmethod
    def _ensure_pages_front_cover_metadata(
        pages: MutableMapping[int, dict[str, Any]],
    ) -> None:
        """Ensure there is a FrontCover page type in pages."""
        if not pages:
            return
        for page in pages.values():
            if page.get(PAGE_TYPE_KEY) == ComicInfoPageTypeEnum.FRONT_COVER:
                return

        # Index 0 is the front cover when it's there, but it need not be:
        # a page whose archive entry reported no size gets no entry at all,
        # and `pages[0]` then raised a KeyError that aborted the entire
        # computed pass. The lowest page present is the cover.
        pages[min(pages)][PAGE_TYPE_KEY] = ComicInfoPageTypeEnum.FRONT_COVER

    def _get_max_page_index(self) -> int:
        if self._path:
            max_page_index = self.get_page_count() - 1
        else:
            # don't strip pages if no path given
            logger.debug("No path given, not computing real pages.")
            max_page_index = maxsize
        return max_page_index

    def _get_computed_merged_pages_metadata(
        self, md: dict[str, Any], pages: dict[int, dict[str, Any]]
    ) -> MutableMapping[int, dict[str, Any]]:
        old_pages: dict[int, dict[str, Any]] = md.get(PAGES_KEY, {})
        max_page_index = self._get_max_page_index()
        trimmed_old_pages = {k: v for k, v in old_pages.items() if k <= max_page_index}
        computed_pages: MutableMapping[int, dict[str, Any]] = AdditiveMerger.merge(
            trimmed_old_pages, pages
        )
        self._ensure_pages_front_cover_metadata(computed_pages)
        return computed_pages

    def _get_computed_pages_metadata(
        self, sub_md: dict[str, Any]
    ) -> dict[str, MutableMapping] | None:
        """Recompute the tag image sizes for the ComicRack PageInfo list."""
        if not self._enable_page_compute_attribute(PAGES_KEY, sub_md):
            return None
        pages = {}
        bookmark = sub_md.get(BOOKMARK_KEY)
        try:
            index = 0
            for info in self.infolist():
                filename = self._get_info_fn(info)
                if self.IMAGE_EXT_RE.search(filename) is None:
                    continue
                size = self._get_info_size(info)
                # height & width could go here.
                if size is not None:
                    computed_page = {}
                    if index == bookmark:
                        computed_page[PAGE_BOOKMARK_KEY] = True
                    computed_page[PAGE_SIZE_KEY] = size
                    pages[index] = computed_page
                index += 1
            # Inside the guard with the scan that feeds it: merging consults
            # the archive too, and warn-and-skip is what every sibling action
            # does with a bad archive.
            if pages:
                pages = self._get_computed_merged_pages_metadata(sub_md, pages)
        except Exception as exc:
            logger.warning(f"{self._path}: Compute pages metadata: {exc}")
        return {PAGES_KEY: pages}
