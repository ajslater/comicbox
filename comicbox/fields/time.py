"""Date & Time fields."""

from datetime import date, datetime
from logging import getLogger

from dateutil import parser
from marshmallow import fields
from ruamel.yaml.timestamp import TimeStamp

from comicbox.fields.fields import DeserializeMeta, StringField

LOG = getLogger(__name__)


class DateField(fields.Date, metaclass=DeserializeMeta):
    """A date only field."""

    def _deserialize(self, value, *_args, **_kwargs) -> date | None:  # type: ignore
        """Liberally parse dates from strings and date-like structures."""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            if value := StringField().deserialize(value):
                dttm = parser.parse(value)
                return dttm.date()
        except Exception:
            LOG.warning(f"Cannot parse date: {value}")
        return None


class DateTimeField(fields.DateTime, metaclass=DeserializeMeta):
    """A Datetime field."""

    def _deserialize(self, value, *_args, **_kwargs) -> datetime | None:  # type: ignore
        """Liberally parse datetmess from strings and datetime-like structures."""
        if isinstance(value, TimeStamp):
            return datetime.fromtimestamp(value.timestamp())  # noqa: DTZ006
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        try:
            if value := StringField().deserialize(value):
                return parser.parse(value)
        except Exception:
            LOG.warning(f"Cannot parse datetime: {value}")
        return None

    def _serialize(self, value, *_args, **_kwargs):
        if value is None:
            return None
        return value.isoformat(timespec="seconds")
