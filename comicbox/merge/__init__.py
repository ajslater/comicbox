"""
Recursive merging for containers.

Every ``Merger`` merges *at the level of the mapping it is handed*: none
of them knows about the comicbox root tag. Callers holding root-wrapped
metadata unwrap it first (see ``ComicboxMerge._merge_metadata_by_source``
and ``ComicboxMetadata._set_computed_merged_metadata``). Before, only
``UpdateMerger`` reached into ROOT_TAG, so the same merger object meant
two different things depending on which call site used it — and handing
it the sub-metadata the other mergers take silently dropped the merge.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping

from typing_extensions import override

from comicbox.merge.mergedeep import Strategy, merge


class Merger(ABC):
    """Base class for merges."""

    @staticmethod
    @abstractmethod
    def merge(dest: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Merge sources into dest, left to right, and return dest."""
        raise NotImplementedError


class AdditiveMerger(Merger):
    """Merge with mergedeep."""

    @override
    @staticmethod
    def merge(dest: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Merge with mergedeep."""
        merge(dest, *sources, strategy=Strategy.ADDITIVE)
        return dest


class ReplaceMerger(Merger):
    """Merge with mergedeep."""

    @override
    @staticmethod
    def merge(dest: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Merge with mergedeep."""
        merge(dest, *sources, strategy=Strategy.REPLACE)
        return dest


class UpdateMerger(Merger):
    """Merge with update."""

    @override
    @staticmethod
    def merge(dest: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Shallowly update dest with each source's top level keys."""
        for source in sources:
            dest.update(source)
        return dest
