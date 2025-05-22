"""Comicbox Computed Date tags."""

from collections.abc import Callable
from datetime import date
from types import MappingProxyType

from loguru import logger

from comicbox.box.computed.identifiers import ComicboxComputedIdentifiers
from comicbox.merge import AdditiveMerger, Merger
from comicbox.schemas.comicbox import (
    COVER_DATE_KEY,
    DATE_KEY,
    DAY_KEY,
    MONTH_KEY,
    YEAR_KEY,
)

_DATE_PART_KEYS = (YEAR_KEY, MONTH_KEY, DAY_KEY)


class ComicboxComputedDate(ComicboxComputedIdentifiers):
    """Comicbox Computed Date tags."""

    def _set_computed_from_date_cover_date(self, old_date: dict, computed_date: dict):
        year: int | None = old_date.get(YEAR_KEY)
        month: int | None = old_date.get(MONTH_KEY)
        day: int | None = old_date.get(DAY_KEY)
        msg = ""
        if all(
            (
                year,
                month,
                day,
            )
        ):
            try:
                dt = date(year, month, day)  # pyright: ignore[reportArgumentType]
                computed_date[COVER_DATE_KEY] = dt
            except ValueError as exc:
                msg = str(exc)
                reason = f"{self._path}: {msg}"
                logger.warning(reason)
        return msg

    @staticmethod
    def _add_date_part(cover_date: date, key: str, computed_date: dict, attr: str):
        computed_date[key] = getattr(cover_date, attr)

    def _set_computed_from_date_parts(
        self, old_date: dict, computed_date: dict, msg: str
    ):
        if COVER_DATE_KEY not in computed_date and (
            cover_date := old_date.get(COVER_DATE_KEY)
        ):
            for key in _DATE_PART_KEYS:
                self._add_date_part(cover_date, key, computed_date, key)
        elif msg:
            # Delete bogus parts if we can't make a date out of them
            delete_keypath = ""
            if msg.startswith("month"):
                delete_keypath = "date.month"
            elif msg.startswith("day"):
                delete_keypath = "date.day"
            if delete_keypath:
                self._extra_delete_keys.add(delete_keypath)

    def _get_computed_from_date(self, sub_data, **_kwargs):
        """Synchronize date parts and cover_date."""
        old_date = sub_data.get(DATE_KEY)
        if not old_date:
            return None
        computed_date = {}

        msg = self._set_computed_from_date_cover_date(old_date, computed_date)
        self._set_computed_from_date_parts(old_date, computed_date, msg)

        if not computed_date:
            return None
        return {DATE_KEY: computed_date}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                # Order is important here
                **ComicboxComputedIdentifiers.COMPUTED_ACTIONS,
                "from date": (_get_computed_from_date, AdditiveMerger),
            }
        )
    )
