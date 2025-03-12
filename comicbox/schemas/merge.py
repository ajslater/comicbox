"""Smartly Deep Merge a comicbox schema dict."""

from collections.abc import Mapping, MutableMapping
from copy import deepcopy

from mergedeep import Strategy, merge

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.comicbox_mixin import PAGES_KEY, STORIES_KEY, ComicboxSchemaMixin

ADDITIVE_STRATEGIES = frozenset({Strategy.ADDITIVE, Strategy.TYPESAFE_ADDITIVE})
# Stories are always replaced because filename titles are unreliably and overzealously parsed and the lists of stories in metadatas are either titles that should be replaced or ordered lists which are difficult to hueristicaly merge
ALWAYS_REPLACE_KEYS = frozenset({STORIES_KEY})


def _create_pages_map(pages: Mapping) -> tuple[Mapping, int]:
    """Create page map from a page list."""
    pages_map = {}
    max_pages_index = -1
    for page in pages:
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


def merge_pages(base_sub_md: MutableMapping, pages: Mapping) -> None:
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
    if strategy not in ADDITIVE_STRATEGIES:
        return replace_dict

    for key in ALWAYS_REPLACE_KEYS:
        value = md_sub_data.pop(key, None)
        if value not in EMPTY_VALUES:
            replace_dict[key] = value
    return replace_dict


def merge_metadata(
    base_md: MutableMapping, md: Mapping, config, strategy: Strategy | None = None
):
    """Merge a dict into another."""
    # TODO passing in strategy and config blows.
    new_md = deepcopy(dict(md))
    base_sub_data = base_md.get(ComicboxSchemaMixin.ROOT_TAG, {})
    new_md_sub_data = new_md.get(ComicboxSchemaMixin.ROOT_TAG, {})

    # Save pages. Remove so it isn't merged normally.
    pages = new_md_sub_data.pop(PAGES_KEY, None)

    if not strategy:
        strategy = Strategy.REPLACE if config.replace_metadata else Strategy.ADDITIVE

    # Pop off the always replace dict.
    replace_dict = _get_always_replace_dict(strategy, new_md_sub_data)

    # Main Merge
    merge(base_md, new_md, strategy=strategy)

    # Merge pages specially
    base_sub_data = base_md.get(ComicboxSchemaMixin.ROOT_TAG, {})
    merge_pages(base_sub_data, pages)

    # Update with the replace dict.
    base_sub_data.update(replace_dict)


def merge_metadata_list(parsed_md_list: list[Mapping], config) -> dict:
    """Pop off complex values before simple update."""
    merged_md = {}
    for parsed_md in parsed_md_list:
        merge_metadata(merged_md, parsed_md, config)
    return merged_md
