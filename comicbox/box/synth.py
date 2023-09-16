"""Synthesize Metadata Methods."""
from collections.abc import Mapping
from logging import getLogger

from marshmallow.utils import is_iterable_but_not_string

from comicbox.box.sources import ComicboxSourcesMixin
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    ORDERED_SET_KEYS,
    PAGES_KEY,
)

LOG = getLogger(__name__)


class ComicboxSynthMixin(ComicboxSourcesMixin):
    """Synthesize Metadata Methods."""

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
    def _create_both_pages_maps(cls, synthed_md, md_pages):
        """Create page maps and compute max page index for synthesizing new page map."""
        old_pages = synthed_md.get(PAGES_KEY, {})
        old_pages_map, max_old_pages_index = cls._create_pages_map(old_pages)
        md_pages_map, max_md_pages_index = cls._create_pages_map(md_pages)
        max_page_index = max(max_old_pages_index, max_md_pages_index)
        return old_pages_map, md_pages_map, max_page_index

    @classmethod
    def _synth_pages(cls, pages, synthed_md):
        """Synthesize new pages map from two metadatas."""
        if not pages:
            return

        # Compute pages maps
        old_pages_map, md_pages_map, max_page_index = cls._create_both_pages_maps(
            synthed_md, pages
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
            synthed_md[PAGES_KEY] = list(new_pages_map.values())
        else:
            synthed_md.pop(PAGES_KEY, None)

    @staticmethod
    def _synth_contributors(synthed_md, md_contributors):
        """Synthesize contributors."""
        try:
            if not md_contributors:
                return
            if CONTRIBUTORS_KEY not in synthed_md:
                synthed_md[CONTRIBUTORS_KEY] = {}
            for role, persons in md_contributors.items():
                if role not in synthed_md[CONTRIBUTORS_KEY]:
                    synthed_md[CONTRIBUTORS_KEY][role] = set()
                synthed_md[CONTRIBUTORS_KEY][role] |= persons
        except KeyError:
            pass

    def _synth_ordered_set(self, synthed_md, key, sequence):
        ordered_set = {}
        for value in synthed_md.get(key, ()):
            ordered_set[value] = None
        for value in sequence:
            ordered_set[value] = None
        return tuple(ordered_set.keys())

    def _synth_key(self, synthed_md, key, value):
        """Synthesize complex values."""
        try:
            if value in EMPTY_VALUES:
                return
            if key not in synthed_md or not is_iterable_but_not_string(value):
                synthed_md[key] = value
            elif key == PAGES_KEY:
                self._synth_pages(value, synthed_md)
            elif key == CONTRIBUTORS_KEY:
                self._synth_contributors(synthed_md, value)
            elif key in ORDERED_SET_KEYS:
                self._synth_ordered_set(synthed_md, key, value)
            elif isinstance(value, (list, tuple)):
                synthed_md[key].extend(value)
            elif isinstance(value, (set, frozenset, Mapping)):
                synthed_md[key].update(value)
        except Exception as exc:
            LOG.warning(f"{self._path} error synthesizing {key} tag: {exc}")

    def synth_metadata_list(self, parsed_md_list, synthed_md):
        """Pop off complex values before simple update."""
        for parsed_md in parsed_md_list:
            for key, value in parsed_md.metadata.items():
                self._synth_key(synthed_md, key, value)
