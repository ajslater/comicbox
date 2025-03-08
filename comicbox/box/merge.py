"""Merge Metadata Methods."""

from collections.abc import Mapping
from logging import getLogger

from mergedeep import Strategy, merge

from comicbox.box.sources import ComicboxSourcesMixin
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.comicbox_mixin import (
    MERGE_MAP_KEYS,
    PAGES_KEY,
    ComicboxSchemaMixin,
)

LOG = getLogger(__name__)


class ComicboxMergeMixin(ComicboxSourcesMixin):
    """Merge Metadata Methods."""

    @staticmethod
    def _create_pages_map(pages):
        """Create page map from a page list."""
        pages_map = {}
        max_pages_index = -1
        for page in pages:
            index = page.get("index", 0)
            pages_map[index] = page
            max_pages_index = max(max_pages_index, index)
        return pages_map, max_pages_index

    @classmethod
    def _create_both_pages_maps(cls, merged_md, md_pages):
        """Create page maps and compute max page index for mergeesizing new page map."""
        old_pages = merged_md.get(PAGES_KEY, {})
        old_pages_map, max_old_pages_index = cls._create_pages_map(old_pages)
        md_pages_map, max_md_pages_index = cls._create_pages_map(md_pages)
        max_page_index = max(max_old_pages_index, max_md_pages_index)
        return old_pages_map, md_pages_map, max_page_index

    @classmethod
    def _merge_pages(cls, pages, merged_md):
        """Merge new pages map from two metadatas."""
        if not pages:
            return

        # Compute pages maps
        old_pages_map, md_pages_map, max_page_index = cls._create_both_pages_maps(
            merged_md, pages
        )
        if max_page_index < 0:
            return

        # Create new_pages_map
        new_pages_map = {}
        for index in range(max_page_index + 1):
            old_page = old_pages_map.get(index, {})
            md_page = md_pages_map.get(index, {})
            new_page = {**old_page, **md_page}
            if new_page:
                new_pages_map[index] = new_page

        # Assign
        if new_pages_map:
            merged_md[PAGES_KEY] = list(new_pages_map.values())
        else:
            merged_md.pop(PAGES_KEY, None)

    def _merge_key(self, merged_md, key, value):
        """Merge complex values."""
        try:
            if value in EMPTY_VALUES:
                return
            if key in merged_md and key == PAGES_KEY:
                self._merge_pages(value, merged_md)
            elif (
                key in merged_md
                and key not in MERGE_MAP_KEYS
                and isinstance(value, Mapping)
            ):
                self.merge_metadata(merged_md[key], value)
            else:
                merge(merged_md, {key: value}, strategy=Strategy.ADDITIVE)

        except Exception as exc:
            LOG.warning(f"{self._path} error merging {key} tag: {exc}")

    def merge_metadata(self, base_md, md):
        """Merge a dict into another."""
        for key, value in md.items():
            if key in self._config.delete_keys:
                continue
            if key != ComicboxSchemaMixin.ROOT_TAG and self._config.replace_metadata:
                base_md[key] = value
            else:
                self._merge_key(base_md, key, value)

    def merge_metadata_list(self, parsed_md_list, merged_md):
        """Pop off complex values before simple update."""
        for parsed_md in parsed_md_list:
            self.merge_metadata(merged_md, parsed_md.metadata)
