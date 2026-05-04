"""Date & Time fields."""

from datetime import date, datetime, timezone
from typing import Any

from dateutil import parser
from loguru import logger
from marshmallow import fields
from ruamel.yaml.timestamp import TimeStamp
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta


class DateField(fields.Date, metaclass=TrapExceptionsMeta):
    """A date only field."""

    def __init__(
        self, *args: Any, serialize_to_str: bool = True, **kwargs: Any
    ) -> None:
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_str = serialize_to_str

    @override
    def _deserialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> date | None:
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
                    dttm = parser.parse(value_str)
                    dt = dttm.date()
            except Exception:
                logger.warning(f"Cannot parse date: {value}")
        return dt

    @override
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
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


class DateTimeField(fields.DateTime, metaclass=TrapExceptionsMeta):
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
            dttm = dttm.replace(tzinfo=timezone.utc)
        return dttm

    @override
    def _deserialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
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
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
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
