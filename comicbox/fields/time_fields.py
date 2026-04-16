"""Date & Time fields."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import ruamel.yaml

from datetime import date, datetime, timezone

from dateutil import parser
from loguru import logger
from marshmallow import fields
from ruamel.yaml.timestamp import TimeStamp
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta


class DateField(fields.Date, metaclass=TrapExceptionsMeta):
    """A date only field."""

    def __init__(self: Any, *args: None, serialize_to_str: bool=True, **kwargs: None) -> None:
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_str = serialize_to_str

    @override
    def _deserialize(self: Any, value: date|str, *args: "dict[str, date]|dict[str, int]|dict[str, str]|ruamel.yaml.CommentedMap|str", **kwargs: bool) -> date | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
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
    def _serialize(self: Any, value: date|fields._D|None, *args: dict[str, date] | dict[str, int] | str | None, **kwargs: None) -> str | float | date | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
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

    def __init__(self: Any, *args: None, serialize_to_iso: bool=True, **kwargs: None) -> None:
        """Configure serialization."""
        super().__init__(*args, **kwargs)
        self._serialize_to_iso = serialize_to_iso

    @staticmethod
    def _ensure_aware(dttm: datetime) -> datetime:
        if not dttm.tzinfo:
            dttm = dttm.replace(tzinfo=timezone.utc)
        return dttm

    @override
    def _deserialize(self: Any, value: datetime|str, *args: "dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, str]|ruamel.yaml.CommentedMap|str|None", **kwargs: bool|None) -> datetime | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
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
    def _serialize(self: Any, value: datetime|fields._D|None, *args: dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, str]]|dict[str, str]|str|None, **kwargs: None) -> str | float | datetime | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
        if value is None:
            return None
        if isinstance(value, datetime):
            value = self._ensure_aware(value)
            if self._serialize_to_iso:
                value = value.isoformat(timespec="seconds").replace("+00:00", "Z")
        else:
            value = StringField()._serialize(value, *args, **kwargs)  # noqa: SLF001
        return value
