"""Unit tests for the vendored mergedeep and the Merger wrappers."""

from __future__ import annotations

from collections import Counter

from comicbox.merge import AdditiveMerger, ReplaceMerger, UpdateMerger
from comicbox.merge.mergedeep import Strategy, merge

#############
# mergedeep #
#############


def test_replace_recurses_into_nested_dicts() -> None:
    """Dict-into-dict merges key-by-key instead of replacing the whole dict."""
    dest = {"a": {"x": 1, "y": 2}, "untouched": 0}
    merge(dest, {"a": {"y": 3, "z": 4}}, strategy=Strategy.REPLACE)
    assert dest == {"a": {"x": 1, "y": 3, "z": 4}, "untouched": 0}


def test_replace_overwrites_lists_and_scalars() -> None:
    """REPLACE swaps conflicting lists and scalars for the source value."""
    dest = {"pages": [1, 2], "count": 2}
    merge(dest, {"pages": [3], "count": 1}, strategy=Strategy.REPLACE)
    assert dest == {"pages": [3], "count": 1}


def test_additive_concatenates_lists() -> None:
    """ADDITIVE extends dest lists with source items, preserving order."""
    dest = {"pages": [1, 2]}
    merge(dest, {"pages": [3, 4]}, strategy=Strategy.ADDITIVE)
    assert dest == {"pages": [1, 2, 3, 4]}


def test_additive_extends_list_from_tuple_source() -> None:
    """A tuple source may extend a list dest."""
    dest = {"pages": [1, 2]}
    merge(dest, {"pages": (3, 4)}, strategy=Strategy.ADDITIVE)
    assert dest == {"pages": [1, 2, 3, 4]}


def test_additive_tuple_dest_is_silently_unchanged() -> None:
    """
    A tuple dest is NOT extended by ADDITIVE merge.

    # NOTE: This looks like a real bug in the vendored mergedeep:
    # _merge_tuple does `dest += tuple(...)` which rebinds the local name
    # (tuples are immutable) and never writes back to dest_parent[key],
    # so tuple-into-tuple merging is a silent no-op. Pinning current
    # behavior here; if it gets fixed this should become (1, 2, 3).
    """
    dest = {"a": (1, 2)}
    merge(dest, {"a": (3,)}, strategy=Strategy.ADDITIVE)
    assert dest == {"a": (1, 2)}


def test_additive_unions_sets() -> None:
    """Set dests are unioned with set or frozenset sources."""
    dest = {"tags": {1, 2}}
    merge(dest, {"tags": frozenset({2, 3})}, strategy=Strategy.ADDITIVE)
    assert dest == {"tags": {1, 2, 3}}


def test_additive_adds_counters() -> None:
    """Counter-into-Counter merging sums counts rather than replacing."""
    dest = {"c": Counter({"x": 1})}
    merge(dest, {"c": Counter({"x": 2, "y": 1})}, strategy=Strategy.ADDITIVE)
    assert dest == {"c": Counter({"x": 3, "y": 1})}


def test_additive_falls_through_to_replace_for_scalars() -> None:
    """Non-collection leaves fall through to REPLACE under ADDITIVE."""
    dest = {"title": "old", "count": 1}
    merge(dest, {"title": "new", "count": 2}, strategy=Strategy.ADDITIVE)
    assert dest == {"title": "new", "count": 2}


def test_deep_nesting_merges_at_every_level() -> None:
    """Recursion applies the strategy at arbitrary depth."""
    dest = {"l1": {"l2": {"l3": {"items": [1], "keep": True}}}}
    merge(dest, {"l1": {"l2": {"l3": {"items": [2]}}}}, strategy=Strategy.ADDITIVE)
    assert dest == {"l1": {"l2": {"l3": {"items": [1, 2], "keep": True}}}}


def test_merge_mutates_dest_in_place_and_returns_it() -> None:
    """Callers rely on dest being mutated and returned, not copied."""
    dest = {"a": [1]}
    result = merge(dest, {"a": [2]}, strategy=Strategy.ADDITIVE)
    assert result is dest
    assert dest == {"a": [1, 2]}


def test_merged_in_source_values_are_deep_copies() -> None:
    """Later mutation of a source must not leak into the merged dest."""
    source_list = [1, [2]]
    dest: dict = {}
    merge(dest, {"new": source_list}, strategy=Strategy.REPLACE)
    source_list[1].append(99)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]
    assert dest == {"new": [1, [2]]}


def test_identical_objects_are_not_merged_twice() -> None:
    """When dest and source hold the same object, the key is skipped."""
    shared = {"x": [1]}
    dest = {"a": shared}
    merge(dest, {"a": shared}, strategy=Strategy.ADDITIVE)
    # Without the identity check the list would self-extend to [1, 1].
    assert dest == {"a": {"x": [1]}}


def test_multiple_sources_apply_left_to_right() -> None:
    """Sources reduce onto dest in order; later sources win conflicts."""
    dest = {"a": 1}
    merge(dest, {"a": 2}, {"a": 3, "b": 4}, strategy=Strategy.REPLACE)
    assert dest == {"a": 3, "b": 4}


###########
# Mergers #
###########


def test_additive_merger_wraps_additive_strategy() -> None:
    """AdditiveMerger concatenates lists recursively and returns dest."""
    dest = {"a": [1], "n": {"b": [2]}}
    result = AdditiveMerger.merge(dest, {"a": [9], "n": {"b": [8], "c": 1}})
    assert result is dest
    assert dest == {"a": [1, 9], "n": {"b": [2, 8], "c": 1}}


def test_replace_merger_wraps_replace_strategy() -> None:
    """ReplaceMerger replaces list leaves instead of concatenating."""
    dest = {"a": [1], "n": {"b": [2]}}
    result = ReplaceMerger.merge(dest, {"a": [9], "n": {"b": [8]}})
    assert result is dest
    assert dest == {"a": [9], "n": {"b": [8]}}


def test_update_merger_shallow_updates_under_root_tag() -> None:
    """UpdateMerger does a shallow dict.update inside the comicbox root tag."""
    dest = {"comicbox": {"a": 1, "b": {"deep": 1}}}
    result = UpdateMerger.merge(dest, {"comicbox": {"b": {"other": 2}, "c": 3}})
    assert result is dest
    # Shallow: the nested 'b' dict is replaced wholesale, not deep-merged.
    assert dest == {"comicbox": {"a": 1, "b": {"other": 2}, "c": 3}}


def test_update_merger_without_root_tag_is_a_noop() -> None:
    """
    UpdateMerger silently drops sources when dest lacks the root tag.

    # NOTE: dest.get(ROOT_TAG, {}) creates a throwaway dict that is
    # updated and discarded, so merging into a dest without a 'comicbox'
    # key loses the source data. Pinning current behavior; callers must
    # pre-shape dest with the root tag.
    """
    dest: dict = {}
    result = UpdateMerger.merge(dest, {"comicbox": {"a": 1}})
    assert result is dest
    assert dest == {}
