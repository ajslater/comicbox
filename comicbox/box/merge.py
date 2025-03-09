"""Merge Metadata Methods."""

from collections.abc import Mapping, MutableMapping
from logging import getLogger

from mergedeep import Strategy, merge

from comicbox.box.sources import ComicboxSourcesMixin
from comicbox.schemas.comicbox_mixin import (
    PAGES_KEY,
    ComicboxSchemaMixin,
)

LOG = getLogger(__name__)


class ComicboxMergeMixin(ComicboxSourcesMixin):
    """Merge Metadata Methods."""

    @staticmethod
    def _create_pages_map(pages: Mapping) -> tuple[Mapping, int]:
        """Create page map from a page list."""
        pages_map = {}
        max_pages_index = -1
        for page in pages:
            index = page.get("index", 0)
            pages_map[index] = page
            max_pages_index = max(max_pages_index, index)
        return pages_map, max_pages_index

    @classmethod
    def _create_both_pages_maps(
        cls, base_sub_md: Mapping, md_pages: Mapping
    ) -> tuple[Mapping, Mapping, int]:
        """Create page maps and compute max page index for mergeesizing new page map."""
        old_pages = base_sub_md.get(PAGES_KEY, {})
        old_pages_map, max_old_pages_index = cls._create_pages_map(old_pages)
        md_pages_map, max_md_pages_index = cls._create_pages_map(md_pages)
        max_page_index = max(max_old_pages_index, max_md_pages_index)
        return old_pages_map, md_pages_map, max_page_index

    @classmethod
    def _merge_pages(cls, base_sub_md: MutableMapping, pages: Mapping) -> None:
        """Merge new pages map from two metadatas."""
        if not pages:
            return

        # Compute pages maps
        old_pages_map, md_pages_map, max_page_index = cls._create_both_pages_maps(
            base_sub_md, pages
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
            base_sub_md[PAGES_KEY] = list(new_pages_map.values())
        else:
            base_sub_md.pop(PAGES_KEY, None)

    @classmethod
    def _merge_metadata(cls, base_md: MutableMapping, md: Mapping, config):
        """Merge a dict into another."""
        base_sub_data = base_md.get(ComicboxSchemaMixin.ROOT_TAG, {})
        md_sub_data = md.get(ComicboxSchemaMixin.ROOT_TAG, {})

        # Delete keys
        for key in config.delete_keys:
            base_sub_data.pop(key, None)
            md_sub_data.pop(key, None)

        # Save pages. Remove so it isn't merged normally.
        pages = md_sub_data.pop(PAGES_KEY, None)

        # Do not delete empties here?

        strategy = Strategy.REPLACE if config.replace_metadata else Strategy.ADDITIVE
        merge(base_md, md, strategy=strategy)

        base_sub_data = base_md.get(ComicboxSchemaMixin.ROOT_TAG, {})
        cls._merge_pages(base_sub_data, pages)

    @classmethod
    def merge_metadata_list(cls, parsed_md_list: list[Mapping], config) -> dict:
        """Pop off complex values before simple update."""
        merged_md = {}
        for parsed_md in parsed_md_list:
            cls._merge_metadata(merged_md, parsed_md, config)
        return merged_md
