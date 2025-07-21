"""Marshmallow number fields."""

import re
from decimal import Decimal

from loguru import logger
from marshmallow import fields
from typing_extensions import override

from comicbox.empty import is_empty
from comicbox.fields.fields import (
    StringField,
    TrapExceptionsMeta,
    half_replace,
)

NumberType = int | float | Decimal
PAGE_COUNT_KEY = "page_count"


class RangedNumberMixin(metaclass=TrapExceptionsMeta):
    """Number range methods."""

    ZERO_FILL: int = 0

    def _set_range(self, minimum: NumberType | None, maximum: NumberType | None):
        self._min = minimum
        self._max = maximum

    @classmethod
    def parse_str(cls, num_obj) -> NumberType | None:
        """Parse numerical string method."""
        raise NotImplementedError

    def _deserialize_pre(self, value) -> NumberType | None:
        if isinstance(value, str):
            value = self.parse_str(value)
        if is_empty(value):
            return None
        return value

    def _deserialize_post(self, value) -> NumberType | None:
        result = value
        if result is not None:
            old_result = result
            if self._min is not None:
                result = max(result, self._min)
            if self._max is not None:
                result = min(result, self._max)
            if old_result != result:
                logger.warning(f"Coerced {old_result} to {result}")
        return result

    def _serialize_post(self, result):
        """Zero pad as_string numbers for sorting."""
        if self.as_string and self.ZERO_FILL and result is not None:  # pyright: ignore[reportAttributeAccessIssue]
            result = result.zfill(self.ZERO_FILL)
        return result


class IntegerField(fields.Integer, RangedNumberMixin):
    """Durable integer field."""

    _FIRST_NUMBER_MATCHER = re.compile(r"\d+")

    @override
    @classmethod
    def parse_str(cls, num_obj) -> int | None:
        """Parse the first number out of volume."""
        num_str: str | None = StringField().deserialize(num_obj)
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

    @override
    def _deserialize(self, value, *args, **kwargs) -> int | None:  #  pyright: ignore[reportIncompatibleMethodOverride]
        value = self._deserialize_pre(value)
        result = super()._deserialize(value, *args, **kwargs)
        return self._deserialize_post(result)  #  pyright: ignore[reportReturnType]

    @override
    def _serialize(self, *args, **kwargs):
        result = super()._serialize(*args, **kwargs)
        return self._serialize_post(result)


class DecimalField(fields.Decimal, RangedNumberMixin):
    """Durable Decimal field that parses some fractions."""

    DECIMAL_MATCHER = re.compile(r"\d*\.?\d+")

    @override
    @classmethod
    def parse_str(cls, num_obj) -> Decimal | None:
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

    @override
    def _deserialize(self, value, *args, **kwargs) -> Decimal | None:  #  pyright: ignore[reportIncompatibleMethodOverride]
        value = self._deserialize_pre(value)
        result = super()._deserialize(value, *args, **kwargs)
        return self._deserialize_post(result)  #  pyright: ignore[reportReturnType]

    @override
    def _serialize(self, *args, **kwargs):
        result = super()._serialize(*args, **kwargs)
        return self._serialize_post(result)


class BooleanField(fields.Boolean, metaclass=TrapExceptionsMeta):
    """A liberally parsed boolean field."""
