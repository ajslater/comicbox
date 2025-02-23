"""Merge Metadata Methods."""

from collections.abc import Mapping
from logging import getLogger

from comicbox.box.sources import ComicboxSourcesMixin
from comicbox.dict_funcs import deep_update
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    NAME_KEY,
    ORDERED_SET_KEYS,
    PAGES_KEY,
    REPRINTS_KEY,
    ROOT_TAG,
    STORIES_KEY,
)
from comicbox.transforms.reprints import sort_reprints

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

    @classmethod
    def _merge_credits(cls, merged_md, md_credits):
        """Merge contributors."""
        try:
            if not md_credits:
                return

            old_credits = merged_md.get(CREDITS_KEY)
            if merged_credits := deep_update(
                old_credits, md_credits, sort=True, case_insensitive=True
            ):
                merged_md[CREDITS_KEY] = merged_credits

        except KeyError:
            pass

    @staticmethod
    def _merge_ordered_set(merged_md, key, sequence):
        """Merge ordered set of strings or named objects."""
        ordered_set = {}
        zipped = (*merged_md.get(key, ()), *sequence)
        for value in zipped:
            if (
                key_value := value.get(NAME_KEY)
                if isinstance(value, Mapping)
                else value
            ):
                ordered_set[key_value] = value
        merged_md[key] = list(ordered_set.values())

    @staticmethod
    def _item_hash(item):
        if isinstance(item, Mapping):
            item = frozenset(item.items())
        elif isinstance(item, set | list | tuple):
            item = frozenset(item)
        if isinstance(item, frozenset):
            return hash(item)
        return item

    @classmethod
    def _merge_list(cls, merged_md, key, sequence):
        """Merge a list, usually eliminating duplicates and sorting."""
        remove_dupes = True
        if remove_dupes:
            old_hashes = {cls._item_hash(item) for item in merged_md[key]}
            for new_item in sequence:
                if (
                    new_item not in EMPTY_VALUES
                    and cls._item_hash(new_item) not in old_hashes
                ):
                    merged_md[key].append(new_item)
        else:
            merged_md[key].extend(sequence)

        do_sort = key != STORIES_KEY
        if do_sort:
            if isinstance(merged_md[key][0], Mapping):
                merged_md[key] = sorted(
                    merged_md[key], key=lambda o: [o.get(NAME_KEY), *sorted(o.items())]
                )
            else:
                merged_md[key] = sorted(merged_md[key])

    def _merge_key(self, merged_md, key, value):  # noqa: C901
        """Merge complex values."""
        try:
            if value in EMPTY_VALUES:
                return
            if key not in merged_md:
                merged_md[key] = value
            elif key == PAGES_KEY:
                self._merge_pages(value, merged_md)
            elif key == CREDITS_KEY:
                self._merge_credits(merged_md, value)
            elif key in ORDERED_SET_KEYS:
                self._merge_ordered_set(merged_md, key, value)
            elif key == REPRINTS_KEY:
                new_value = merged_md[key] + value
                merged_md[key] = sort_reprints(new_value)
            elif isinstance(value, list | tuple):
                self._merge_list(merged_md, key, value)
            elif isinstance(value, set | frozenset):
                merged_md[key].update(value)
            elif isinstance(value, Mapping):
                self.merge_metadata(merged_md[key], value)
            else:
                # be sure to update
                merged_md[key] = value

        except Exception as exc:
            LOG.warning(f"{self._path} error merging {key} tag: {exc}")

    def merge_metadata(self, base_md, md):
        """Merge a dict into another."""
        for key, value in md.items():
            if key in self._config.delete_keys:
                continue
            if key != ROOT_TAG and self._config.replace_metadata:
                base_md[key] = value
            else:
                self._merge_key(base_md, key, value)

    def merge_metadata_list(self, parsed_md_list, merged_md):
        """Pop off complex values before simple update."""
        for parsed_md in parsed_md_list:
            self.merge_metadata(merged_md, parsed_md.metadata)
