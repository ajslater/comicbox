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

    def __init__(self, *args, serialize_to_str=True, **kwargs):
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_str = serialize_to_str

    @override
    def _deserialize(self, value, *args, **kwargs) -> date | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
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

    @override
    def _serialize(self, value, *args, **kwargs) -> str | float | None | date:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
        if self._serialize_to_str:
            return super()._serialize(value, *args, **kwargs)
        return value


class DateTimeField(fields.DateTime, metaclass=TrapExceptionsMeta):
    """A Datetime field."""

    def __init__(self, *args, serialize_to_iso=True, **kwargs):
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_iso = serialize_to_iso

    @staticmethod
    def _ensure_aware(dttm: datetime):
        if not dttm.tzinfo:
            dttm = dttm.replace(tzinfo=timezone.utc)
        return dttm

    @override
    def _deserialize(self, value, *args, **kwargs) -> datetime | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
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
    def _serialize(self, value, *args, **kwargs) -> str | None | datetime:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
        if value is None:
            return None
        if isinstance(value, datetime):
            value = self._ensure_aware(value)
            if self._serialize_to_iso:
                value = value.isoformat(timespec="seconds").replace("+00:00", "Z")
        return value
