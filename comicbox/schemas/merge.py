"""Smartly Deep Merge a comicbox schema dict."""

from collections.abc import Mapping, MutableMapping

from comicbox.empty import is_empty
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger
from comicbox.schemas.comicbox_mixin import STORIES_KEY, ComicboxSchemaMixin

ADDITIVE_MERGERS = frozenset({AdditiveMerger})
# Stories are always replaced because filename titles are unreliably and
# overzealously parsed and the lists of stories in metadatas are either
# titles that should be replaced or ordered lists which are difficult to
# hueristicaly merge
ALWAYS_REPLACE_KEYS = frozenset({STORIES_KEY})


def _get_always_replace_dict(merger, md_sub_data):
    """Get values for top level keys that are always replaced."""
    replace_dict = {}
    if merger not in ADDITIVE_MERGERS:
        return replace_dict

    for key in ALWAYS_REPLACE_KEYS:
        value = md_sub_data.pop(key, None)
        if not is_empty(value):
            replace_dict[key] = value
    return replace_dict


def merge_metadata(
    base_md: MutableMapping,
    new_md: Mapping,
    config,
    merger: type[Merger] | None = None,
):
    """Merge a dict into another."""
    base_sub_md = base_md[ComicboxSchemaMixin.ROOT_TAG]
    new_sub_md = new_md.get(ComicboxSchemaMixin.ROOT_TAG)
    if not new_sub_md:
        return

    # TODO passing in strategy and config blows.
    if not merger:
        merger = ReplaceMerger if config.replace_metadata else AdditiveMerger

    # Pop off the always replace dict.
    replace_dict = _get_always_replace_dict(merger, new_sub_md)

    merger.merge(base_sub_md, new_sub_md)

    # Update with the replace dict.
    ReplaceMerger.merge(base_sub_md, replace_dict)


def merge_metadata_list(parsed_md_list: list[Mapping], config) -> dict:
    """Pop off complex values before simple update."""
    merged_md = {ComicboxSchemaMixin.ROOT_TAG: {}}
    for parsed_md in parsed_md_list:
        merge_metadata(merged_md, parsed_md, config)
    return merged_md
