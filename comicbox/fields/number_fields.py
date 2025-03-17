"""Marshmallow number fields."""

import re
from decimal import Decimal
from logging import getLogger

from marshmallow import fields

from comicbox.fields.fields import (
    EMPTY_VALUES,
    StringField,
    TrapExceptionsMeta,
    half_replace,
)

LOG = getLogger(__name__)
NumberType = int | float | Decimal


class RangedNumberMixin(fields.Number, metaclass=TrapExceptionsMeta):
    """Number range methods."""

    def _set_range(self, minimum: NumberType | None, maximum: NumberType | None):
        self._min = minimum
        self._max = maximum

    def __init__(
        self,
        *args,
        minimum: NumberType | None = None,
        maximum: NumberType | None = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)

    @classmethod
    def parse_str(cls, num_obj) -> NumberType | None:
        """Parse numerical string method."""
        raise NotImplementedError

    def _deserialize(self, value, *args, **kwargs) -> NumberType | None:
        if isinstance(value, str):
            value = self.parse_str(value)
        if value in EMPTY_VALUES:
            return None
        result = super()._deserialize(value, *args, **kwargs)
        if result is not None:
            old_result = result
            if self._min is not None:
                result = max(result, self._min)
            if self._max is not None:
                result = min(result, self._max)
            if old_result != result:
                LOG.warning(f"Coerced {old_result} to {result}")
        return result


class IntegerField(fields.Integer, RangedNumberMixin):
    """Durable integer field."""

    _FIRST_NUMBER_MATCHER = re.compile(r"\d+")

    @classmethod
    def parse_str(cls, num_obj):
        """Parse the first number out of volume."""
        num_str: str | None = StringField().deserialize(num_obj)  # type: ignore[reportAssignmentType]
        if not num_str:
            return None
        match: re.Match | None = cls._FIRST_NUMBER_MATCHER.search(num_str)
        if match:
            return int(match.group())
        return None

    def __init__(
        self,
        *args,
        minimum: int | None = None,
        maximum: int | None = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)


class DecimalField(fields.Decimal, RangedNumberMixin):
    """Durable Decimal field that parses some fractions."""

    DECIMAL_MATCHER = re.compile(r"\d*\.?\d+")

    @classmethod
    def parse_str(cls, num_obj):
        """Fix half glyphs."""
        num_str: str | None = StringField().deserialize(num_obj)  # type: ignore[reportAssignmentType]
        if not num_str:
            return None
        num_str = num_str.replace(" ", "")
        num_str = half_replace(num_str)
        match = cls.DECIMAL_MATCHER.search(num_str)
        if match:
            return Decimal(match.group())
        return None

    def __init__(
        self,
        *args,
        minimum: Decimal | None = None,
        maximum: Decimal | None = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)


class BooleanField(fields.Boolean, metaclass=TrapExceptionsMeta):
    """A liberally parsed boolean field."""
