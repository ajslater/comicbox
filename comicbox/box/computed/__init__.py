"""Computed metadata methods."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from comicfn2dict.regex import ORIGINAL_FORMAT_RE
from deepdiff import DeepDiff
from loguru import logger

from comicbox.box.computed.stories_title import ComicboxComputedStoriesTitle
from comicbox.formats.base.fields.enum_fields import OriginalFormatField
from comicbox.formats.comicbox.schema import (
    ORIGINAL_FORMAT_KEY,
    REPRINTS_KEY,
    SCAN_INFO_KEY,
    ComicboxSchemaMixin,
)
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None
    merger: type[Merger] | None = AdditiveMerger


class ComicboxComputed(ComicboxComputedStoriesTitle):
    """Computed metadata methods."""

    def _get_computed_from_scan_info(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, Any] | None:
        """Parse scan_info for original format info."""
        if ORIGINAL_FORMAT_KEY in self._config.general.delete_keys or not sub_data:
            return None
        scan_info = sub_data.get(SCAN_INFO_KEY)
        if not scan_info or sub_data.get(ORIGINAL_FORMAT_KEY):
            return None

        match = ORIGINAL_FORMAT_RE.search(scan_info)
        if not match:
            return None
        try:
            # Normalize through the field so the computed value matches the
            # canonical enum form every other original_format path uses.
            original_format = OriginalFormatField().deserialize(
                match.group(ORIGINAL_FORMAT_KEY)
            )
        except Exception as exc:
            # Garbage scan_info must not abort the whole computed pass —
            # warn-and-skip matches the other computed actions.
            logger.warning(f"Could not normalize original_format from scan_info: {exc}")
            return None
        if not original_format:
            return None
        return {ORIGINAL_FORMAT_KEY: original_format}

    def _get_computed_from_reprints(
        self, sub_data: dict[str, Any]
    ) -> dict[str, list] | None:
        """Consolidate reprints."""
        if REPRINTS_KEY in self._config.general.delete_keys or not sub_data:
            return None
        old_reprints = sub_data.get(REPRINTS_KEY)
        if not old_reprints:
            return None
        new_reprints = []
        merged_indexes = set()
        for index, old_reprint in enumerate(old_reprints):
            if index in merged_indexes:
                continue
            for sub_index, compare_old_reprint in enumerate(old_reprints[index:]):
                diff = DeepDiff(
                    old_reprint,
                    compare_old_reprint,
                    ignore_order=True,
                    ignore_string_case=True,
                    ignore_encoding_errors=True,
                )
                if "values_changed" not in diff:
                    AdditiveMerger.merge(old_reprint, compare_old_reprint)
                    merged_indexes.add(index + sub_index)
            new_reprints.append(old_reprint)

        if len(old_reprints) != len(new_reprints):
            return {REPRINTS_KEY: new_reprints}
        return None

    def _get_delete_keys(self, _sub_data: Mapping) -> tuple | None:
        if not self._config.general.delete_keys:
            return None
        return tuple(sorted(self._config.general.delete_keys | self._extra_delete_keys))

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                # Order is important here
                **ComicboxComputedStoriesTitle.COMPUTED_ACTIONS,
                "from reprints": (_get_computed_from_reprints, ReplaceMerger),
                "from scan_info": (_get_computed_from_scan_info, AdditiveMerger),
                "Delete Keys": (_get_delete_keys, None),
            }
        )
    )

    def _set_computed_metadata(self) -> None:
        computed_list = []
        merged_md = self.get_merged_metadata()
        # Deep copy: actions receive sub_data and some (reprints) merge
        # entries in place; without the copy they'd silently mutate the
        # cached merged metadata they're supposed to derive from.
        sub_data = deepcopy(dict(merged_md.get(ComicboxSchemaMixin.ROOT_TAG, {})))

        # Compute each
        for label, actions in self.COMPUTED_ACTIONS.items():
            method, merger = actions
            sub_md = method(self, sub_data)
            if not sub_md:
                continue

            md = {ComicboxSchemaMixin.ROOT_TAG: sub_md}
            computed_data = ComputedData(label, md, merger)
            computed_list.append(computed_data)

        # Set values
        self._computed = tuple(computed_list)
        self._computed_dict_formats = self._dict_formats

    def get_computed_metadata(self) -> tuple:
        """Get the computed metadata for printing."""
        # Recompute when the dict-format context changed: pages/page_count
        # computation consults _dict_formats, so a result memoized under
        # one to_dict() format must not leak into calls under another.
        if not self._computed or self._computed_dict_formats != self._dict_formats:
            self._set_computed_metadata()
        return self._computed
