"""Date & Time fields."""

import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from dateutil import parser
from loguru import logger
from marshmallow import fields
from ruamel.yaml.timestamp import TimeStamp

from comicbox.formats.base.fields.fields import StringField

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


# Two defaults that differ in every part: a part the string holds parses
# the same over both, and a part it lacks takes each default's.
_PROBES = (datetime(2000, 1, 1), datetime(2001, 2, 2))  # noqa: DTZ001


@dataclass(frozen=True, slots=True)
class DateParts:
    """The parts of a date a string holds; a part it lacks is None."""

    year: int | None
    month: int | None
    day: int | None

    @property
    def whole(self) -> bool:
        """Whether the string holds a whole date."""
        return None not in (self.year, self.month, self.day)


def date_parts(text: str) -> DateParts | None:
    """
    Parse the parts of a date a string holds, filling in none of the rest.

    dateutil fills a missing part from its default, today's date unless told
    otherwise, so ``2006-07`` parsed on the 14th became the 14th of July.
    None for a string that holds no date at all.
    """
    try:
        first, second = (parser.parse(text, default=probe) for probe in _PROBES)
    except (ValueError, OverflowError):
        return None
    parts = (
        (first.year, second.year),
        (first.month, second.month),
        (first.day, second.day),
    )
    year, month, day = (one if one == other else None for one, other in parts)
    return DateParts(year, month, day)


class DateField(fields.Date):
    """
    A date only field.

    A string that holds only part of a date, such as CoMet's ``2006`` or
    ``2006-07``, is not a date, and is kept as the string: the comicbox
    date schema keeps its parts as the year and month.
    """

    def __init__(
        self, *args: Any, serialize_to_str: bool = True, **kwargs: Any
    ) -> None:
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_str = serialize_to_str

    @override
    def _deserialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[incompatible-method-override]
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> date | str | None:
        """Liberally parse dates from strings and date-like structures."""
        dt = None
        if isinstance(value, datetime):
            # datetime is a subclass of date. order like this.
            dt = value.date()
        elif isinstance(value, date):
            dt = value
        else:
            try:
                if value_str := StringField().deserialize(value):
                    return self._deserialize_text(value_str)
            except Exception:
                logger.warning(f"Cannot parse date: {value}")
        return dt

    @staticmethod
    def _deserialize_text(text: str) -> date | str | None:
        """Parse a whole date, keep a partial one as text, refuse the rest."""
        parts = date_parts(text)
        if parts is None or (parts.year is None and parts.month is None):
            reason = f"Not a date: {text}"
            raise ValueError(reason)
        if not parts.whole:
            return text
        return date(parts.year, parts.month, parts.day)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]

    @override
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[incompatible-method-override]
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> str | float | date | None:
        if value is None:
            return None
        if self._serialize_to_str:
            if isinstance(value, date):
                value = super()._serialize(value, *args, **kwargs)
            else:
                value = StringField()._serialize(value, *args, **kwargs)  # noqa: SLF001
        return value


class DateTimeField(fields.DateTime):
    """A Datetime field."""

    def __init__(
        self, *args: Any, serialize_to_iso: bool = True, **kwargs: Any
    ) -> None:
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_iso = serialize_to_iso

    @staticmethod
    def _ensure_aware(dttm: datetime) -> datetime:
        if not dttm.tzinfo:
            dttm = dttm.replace(tzinfo=UTC)
        return dttm

    @override
    def _deserialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[incompatible-method-override]
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> datetime | None:
        """Liberally parse datetimes from strings and datetime-like structures."""
        dttm = None
        match value:
            case TimeStamp():
                dttm = datetime(
                    value.year,
                    value.month,
                    value.day,
                    value.hour,
                    value.minute,
                    value.second,
                    value.microsecond,
                    value.tzinfo,
                )
            case datetime():
                dttm = value
            case date():
                dttm = datetime.combine(value, datetime.min.time())
            case _:
                try:
                    if value_str := StringField().deserialize(value):
                        dttm = parser.parse(value_str)
                except Exception:
                    logger.warning(f"Cannot parse datetime: {value}")
        if dttm is not None:
            dttm = self._ensure_aware(dttm)
        return dttm

    @override
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[incompatible-method-override]
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> str | float | datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            value = self._ensure_aware(value)
            if self._serialize_to_iso:
                value = value.isoformat(timespec="seconds").replace("+00:00", "Z")
        else:
            value = StringField()._serialize(value, *args, **kwargs)  # noqa: SLF001
        return value
