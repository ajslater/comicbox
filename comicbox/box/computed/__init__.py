"""Computed metadata methods."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from logging import getLogger
from types import MappingProxyType

from comicfn2dict.regex import ORIGINAL_FORMAT_RE
from deepdiff import DeepDiff

from comicbox.box.archive import archive_close
from comicbox.box.computed.identifiers import ComicboxComputedIdentifers
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger
from comicbox.schemas.comicbox import (
    COVER_DATE_KEY,
    DATE_KEY,
    DAY_KEY,
    MONTH_KEY,
    ORIGINAL_FORMAT_KEY,
    REPRINTS_KEY,
    SCAN_INFO_KEY,
    YEAR_KEY,
    ComicboxSchemaMixin,
)

LOG = getLogger(__name__)
_DATE_PART_KEYS = (YEAR_KEY, MONTH_KEY, DAY_KEY)


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None
    merger: type[Merger] | None = AdditiveMerger


class ComicboxComputed(ComicboxComputedIdentifers):
    """Computed metadata methods."""

    @staticmethod
    def _add_date_part(cover_date: date, key: str, computed_date: dict, attr: str):
        computed_date[key] = getattr(cover_date, attr)

    def _get_computed_from_date(self, sub_data, **_kwargs):
        """Synchronize date parts and cover_date."""
        old_date = sub_data.get(DATE_KEY)
        if not old_date:
            return None
        computed_date = {}
        year = old_date.get(YEAR_KEY)
        month = old_date.get(MONTH_KEY)
        day = old_date.get(DAY_KEY)
        msg = ""
        if all(
            (
                year,
                month,
                day,
            )
        ):
            try:
                computed_date[COVER_DATE_KEY] = date(year, month, day)
            except ValueError as exc:
                msg = str(exc)
                reason = f"{self._path}: {msg}"
                LOG.warning(reason)

        if COVER_DATE_KEY not in computed_date and (
            cover_date := old_date.get(COVER_DATE_KEY)
        ):
            for key in _DATE_PART_KEYS:
                self._add_date_part(cover_date, key, computed_date, key)
        elif msg:
            if msg.startswith("month"):
                self._config.delete_keys = frozenset(
                    self._config.delelte_keys | {"date.month"}
                )
            elif msg.startswith("day"):
                self._config.delete_keys = frozenset(
                    self._config.delete_keys | {"date.day"}
                )

        if not computed_date:
            return None
        return {DATE_KEY: computed_date}

    def _get_computed_from_scan_info(self, sub_data, **_kwargs):
        """Parse scan_info for original format info."""
        if ORIGINAL_FORMAT_KEY in self._config.delete_keys or not sub_data:
            return None
        scan_info = sub_data.get(SCAN_INFO_KEY)
        if not scan_info or sub_data.get(ORIGINAL_FORMAT_KEY):
            return None

        match = ORIGINAL_FORMAT_RE.search(scan_info)
        if not match:
            return None
        return {ORIGINAL_FORMAT_KEY: match.group(ORIGINAL_FORMAT_KEY)}

    def _get_computed_from_reprints(self, sub_data):
        """Consolidate reprints."""
        if REPRINTS_KEY in self._config.delete_keys or not sub_data:
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

    def _get_delete_keys(self, _sub_data: Mapping):
        if not self._config.delete_keys:
            return None
        return tuple(sorted(self._config.delete_keys))

    _COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                # Order is important here
                **ComicboxComputedIdentifers.COMPUTED_ACTIONS,
                "from date": (_get_computed_from_date, AdditiveMerger),
                "from reprints": (_get_computed_from_reprints, ReplaceMerger),
                "from scan_info": (_get_computed_from_scan_info, AdditiveMerger),
                "Delete Keys": (_get_delete_keys, None),
            }
        )
    )

    def _set_computed_metadata(self):
        computed_list = []
        merged_md = self.get_merged_metadata()
        sub_data = merged_md.get(ComicboxSchemaMixin.ROOT_TAG, {})

        # Compute each
        for label, actions in self._COMPUTED_ACTIONS.items():
            method, merger = actions
            sub_md = method(self, sub_data)
            if not sub_md:
                continue

            md = {ComicboxSchemaMixin.ROOT_TAG: sub_md}
            computed_data = ComputedData(label, md, merger)
            computed_list.append(computed_data)

        # Set values
        self._computed = tuple(computed_list)

    @archive_close
    def get_computed_metadata(self):
        """Get the computed metadata for printing."""
        if not self._computed:
            self._set_computed_metadata()
        return self._computed
