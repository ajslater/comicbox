"""Comicbox Computed Pages."""

from collections.abc import Callable, Mapping
from sys import maxsize
from types import MappingProxyType

from loguru import logger

from comicbox.box.computed.notes import ComicboxComputedNotes
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger
from comicbox.schemas.comicbox import (
    BOOKMARK_KEY,
    PAGE_BOOKMARK_KEY,
    PAGE_COUNT_KEY,
    PAGE_SIZE_KEY,
    PAGE_TYPE_KEY,
    PAGES_KEY,
)

_ENABLE_PAGE_COMPUTE_ATTRS = MappingProxyType(
    {
        PAGE_COUNT_KEY: ("compute_page_count", "HAS_PAGE_COUNT"),
        PAGES_KEY: ("compute_pages", "HAS_PAGES"),
    }
)


class ComicboxComputedPages(ComicboxComputedNotes):
    """Comicbox Computed Pages."""

    def _enable_page_compute_attribute(self, key: str, sub_md: Mapping):
        """Determine if we should compute this attribute."""
        if key in self._config.delete_keys or not sub_md or not self._path:
            return False
        formats = frozenset(
            self._config.computed.all_write_formats | self._dict_formats
        )
        config_attr, schema_attr = _ENABLE_PAGE_COMPUTE_ATTRS[key]
        return getattr(self._config, config_attr, False) and (
            any(getattr(fmt.value.schema_class, schema_attr, False) for fmt in formats)
        )

    def _get_computed_page_count_metadata(self, sub_md):
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

    def _ensure_pages_front_cover_metadata(self, pages):
        """Ensure there is a FrontCover page type in pages."""
        for page in pages.values():
            if page.get(PAGE_TYPE_KEY) == ComicInfoPageTypeEnum.FRONT_COVER:
                return

        pages[0][PAGE_TYPE_KEY] = ComicInfoPageTypeEnum.FRONT_COVER

    def _get_max_page_index(self):
        if self._path:
            max_page_index = self.get_page_count() - 1
        else:
            # don't strip pages if no path given
            logger.debug("No path given, not computing real pages.")
            max_page_index = maxsize
        return max_page_index

    def _get_computed_merged_pages_metadata(self, md, pages):
        old_pages = md.get(PAGES_KEY, {})
        max_page_index = self._get_max_page_index()
        trimmed_old_pages = {k: v for k, v in old_pages.items() if k <= max_page_index}
        computed_pages = AdditiveMerger.merge(trimmed_old_pages, pages)
        self._ensure_pages_front_cover_metadata(computed_pages)
        return computed_pages

    def _get_computed_pages_metadata(self, sub_md):
        """Recompute the tag image sizes for the ComicRack PageInfo list."""
        if not self._enable_page_compute_attribute(PAGES_KEY, sub_md):
            return None
        pages = {}
        bookmark = sub_md.get(BOOKMARK_KEY)
        try:
            index = 0
            infolist = self.infolist()
            for info in infolist:
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
        except Exception as exc:
            logger.warning(f"{self._path}: Compute pages metadata: {exc}")
        if pages:
            pages = self._get_computed_merged_pages_metadata(sub_md, pages)
        return {PAGES_KEY: pages}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                "Page Count": (_get_computed_page_count_metadata, ReplaceMerger),
                "Pages": (_get_computed_pages_metadata, ReplaceMerger),
                **ComicboxComputedNotes.COMPUTED_ACTIONS,
            }
        )
    )
