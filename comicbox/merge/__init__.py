"""Recursive merging for containers."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping

from typing_extensions import override

from comicbox.merge.mergedeep import Strategy, merge
from comicbox.schemas.comicbox import ComicboxSchemaMixin


class Merger(ABC):
    """Base class for merges."""

    @staticmethod
    @abstractmethod
    def merge(dest: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Implement a merge method."""
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
        """Merge with update."""
        dest_sub_md = dest.get(ComicboxSchemaMixin.ROOT_TAG, {})
        for source in sources:
            source_sub_md = source.get(ComicboxSchemaMixin.ROOT_TAG, {})
            dest_sub_md.update(source_sub_md)
        return dest
