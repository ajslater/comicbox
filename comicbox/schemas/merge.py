"""Smartly Deep Merge a comicbox schema dict."""

from collections.abc import Mapping, MutableMapping
from copy import deepcopy

from deepmerge.merger import Merger

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.merge import ADD_UNIQUE_MERGER, REPLACE_MERGER
from comicbox.schemas.comicbox_mixin import PAGES_KEY, STORIES_KEY, ComicboxSchemaMixin

ADDITIVE_MERGERS = frozenset({ADD_UNIQUE_MERGER})
# Stories are always replaced because filename titles are unreliably and overzealously parsed and the lists of stories in metadatas are either titles that should be replaced or ordered lists which are difficult to hueristicaly merge
ALWAYS_REPLACE_KEYS = frozenset({STORIES_KEY})


def _create_pages_map(pages: Mapping | None) -> tuple[Mapping, int]:
    """Create page map from a page list."""
    pages_map = {}
    max_pages_index = -1
    if pages is None:
        return pages_map, max_pages_index
    for page in pages:
        if page is None:
            continue
        index = page.get("index", 0)
        pages_map[index] = page
        max_pages_index = max(max_pages_index, index)
    return pages_map, max_pages_index


def _create_both_pages_maps(
    base_sub_md: Mapping, md_pages: Mapping
) -> tuple[Mapping, Mapping, int]:
    """Create page maps and compute max page index for mergeesizing new page map."""
    old_pages = base_sub_md.get(PAGES_KEY, {})
    old_pages_map, max_old_pages_index = _create_pages_map(old_pages)
    md_pages_map, max_md_pages_index = _create_pages_map(md_pages)
    max_page_index = max(max_old_pages_index, max_md_pages_index)
    return old_pages_map, md_pages_map, max_page_index


def merge_pages(base_sub_md: MutableMapping, pages: Mapping | None) -> None:
    """Merge new pages map from two metadatas."""
    if not pages:
        return

    # Compute pages maps
    old_pages_map, md_pages_map, max_page_index = _create_both_pages_maps(
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


def _get_always_replace_dict(strategy, md_sub_data):
    """Get values for top level keys that are always replaced."""
    replace_dict = {}
    if strategy not in ADDITIVE_MERGERS:
        return replace_dict

    for key in ALWAYS_REPLACE_KEYS:
        value = md_sub_data.pop(key, None)
        if value not in EMPTY_VALUES:
            replace_dict[key] = value
    return replace_dict


def merge_metadata(
    base_md: MutableMapping, new_md: Mapping, config, merger: Merger | None = None
):
    """Merge a dict into another."""
    base_sub_md = base_md[ComicboxSchemaMixin.ROOT_TAG]
    new_sub_md = new_md.get(ComicboxSchemaMixin.ROOT_TAG)
    if not new_sub_md:
        return
    # TODO passing in strategy and config blows.
    new_sub_md = deepcopy(dict(new_sub_md))

    if not merger:
        merger = REPLACE_MERGER if config.replace_metadata else ADD_UNIQUE_MERGER

    # Pop off the always replace dict.
    if merger in ADDITIVE_MERGERS:
        replace_dict = _get_always_replace_dict(merger, new_sub_md)
        # Save pages. Remove so it isn't merged normally.
        pages = new_sub_md.pop(PAGES_KEY, None)
    else:
        replace_dict = pages = {}

    merger.merge(base_sub_md, new_sub_md)

    if merger in ADDITIVE_MERGERS:
        # Merge pages specially
        merge_pages(base_sub_md, pages)
        # Update with the replace dict.
        base_sub_md.update(replace_dict)


def merge_metadata_list(parsed_md_list: list[Mapping], config) -> dict:
    """Pop off complex values before simple update."""
    merged_md = {ComicboxSchemaMixin.ROOT_TAG: {}}
    for parsed_md in parsed_md_list:
        merge_metadata(merged_md, parsed_md, config)
    return merged_md
