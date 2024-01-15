"""Marshmallow number fields."""
import re
from decimal import Decimal
from logging import getLogger
from typing import Optional, Union

from marshmallow import fields

from comicbox.fields.fields import (
    EMPTY_VALUES,
    DeserializeMeta,
    StringField,
    half_replace,
)

LOG = getLogger(__name__)
NumberType = Union[int, float, Decimal]


class RangedNumberMixin(fields.Number, metaclass=DeserializeMeta):
    """Number range methods."""

    def _set_range(self, minimum: Optional[NumberType], maximum: Optional[NumberType]):
        self._min = minimum
        self._max = maximum

    def __init__(
        self,
        *args,
        minimum: Optional[NumberType] = None,
        maximum: Optional[NumberType] = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)

    @classmethod
    def parse_str(cls, num_str) -> Optional[NumberType]:
        """Parse numerical string method."""
        raise NotImplementedError

    def _deserialize(self, value, *args, **kwargs) -> Optional[NumberType]:
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


class IntegerField(RangedNumberMixin, fields.Integer):
    """Durable integer field."""

    _FIRST_NUMBER_MATCHER = re.compile(r"\d+")

    @classmethod
    def parse_str(cls, num_str):
        """Parse the first number out of volume."""
        num_str = StringField().deserialize(num_str)
        if not num_str:
            return None
        match = cls._FIRST_NUMBER_MATCHER.search(num_str)
        if match:
            return int(match.group())
        return None

    def __init__(
        self,
        *args,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)


class DecimalField(RangedNumberMixin, fields.Decimal):
    """Durable Decimal field that parses some fractions."""

    DECIMAL_MATCHER = re.compile(r"\d*\.?\d+")

    @classmethod
    def parse_str(cls, num_str):
        """Fix half glyphs."""
        num_str = StringField().deserialize(num_str)
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
        minimum: Optional[Decimal] = None,
        maximum: Optional[Decimal] = None,
        **kwargs,
    ):
        """Set the min and max value."""
        super().__init__(*args, **kwargs)
        self._set_range(minimum, maximum)


class BooleanField(fields.Boolean, metaclass=DeserializeMeta):
    """A liberally parsed boolean field."""
