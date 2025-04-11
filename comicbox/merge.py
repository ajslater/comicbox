"""Recursive merging for containers."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping

from mergedeep import Strategy, merge


class Merger(ABC):
    """Base class for merges."""

    @staticmethod
    @abstractmethod
    def merge(destination: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Implement a merge method."""
        raise NotImplementedError


class AdditiveMerger(Merger):
    """Merge with mergedeep."""

    @staticmethod
    def merge(destination: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Merge with mergedeep."""
        merge(destination, *sources, strategy=Strategy.ADDITIVE)
        return destination


class ReplaceMerger(Merger):
    """Merge with update."""

    @staticmethod
    def merge(destination: MutableMapping, *sources: Mapping) -> MutableMapping:
        """Merge with update."""
        for source in sources:
            destination.update(source)
        return destination
