"""Date & Time fields."""

from datetime import date, datetime, timezone

from dateutil import parser
from loguru import logger
from marshmallow import fields
from ruamel.yaml.timestamp import TimeStamp
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta


class DateField(fields.Date, metaclass=TrapExceptionsMeta):
    """A date only field."""

    @override
    def _deserialize(self, value, *_args, **_kwargs) -> date | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Liberally parse dates from strings and date-like structures."""
        dt = None
        if isinstance(value, date):
            dt = value
        elif isinstance(value, datetime):
            dt = value.date()
        else:
            try:
                if value_str := StringField().deserialize(value):
                    dttm = parser.parse(value_str)
                    dt = dttm.date()
            except Exception:
                logger.warning(f"Cannot parse date: {value}")
        return dt


class DateTimeField(fields.DateTime, metaclass=TrapExceptionsMeta):
    """A Datetime field."""

    @staticmethod
    def _ensure_aware(dttm: datetime):
        if not dttm.tzinfo:
            dttm = dttm.replace(tzinfo=timezone.utc)
        return dttm

    @override
    def _deserialize(self, value, *_args, **_kwargs) -> datetime | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Liberally parse datetimes from strings and datetime-like structures."""
        dttm = None
        if isinstance(value, TimeStamp):
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
        elif isinstance(value, datetime):
            dttm = value
        elif isinstance(value, date):
            dttm = datetime.combine(value, datetime.min.time())
        else:
            try:
                if value_str := StringField().deserialize(value):
                    dttm = parser.parse(value_str)
            except Exception:
                logger.warning(f"Cannot parse datetime: {value}")
        if dttm is not None:
            dttm = self._ensure_aware(dttm)
        return dttm

    @override
    def _serialize(self, value, *_args, **_kwargs):
        if value is None:
            return None
        value = self._ensure_aware(value)
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")
