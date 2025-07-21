"""Custom Marshmallow fields."""

import re
from abc import ABCMeta
from decimal import Decimal
from enum import Enum

from loguru import logger
from marshmallow import fields
from marshmallow.exceptions import ValidationError
from typing_extensions import override

_STRING_EMPTY_VALUES = (None, "")
_LEADING_ZERO_RE = re.compile(r"^(0+)(\w)")
_HALF_RE = re.compile(r"(½|1/2)")


class TrapExceptionsMeta(ABCMeta):
    """Wrap the deserialize method to never throw."""

    _WRAP_METHODS = ("deserialize",)

    @classmethod
    def wrap_method(cls, method):
        """Wrap method to never throw."""

        def wrapper(self, value, attr, *args, **kwargs):
            """Trap exceptions, log and return None."""
            try:
                return method(self, value, attr, *args, **kwargs)
            except Exception as exc:
                # Log the exception
                cls_name = self.__class__.__name__
                logger.warning(
                    f"Could not deserialize {attr}:{value} as {cls_name} - {exc}"
                )
                return None

        return wrapper

    def __new__(cls, name, bases, attrs):
        """Wrap the deserialize method."""
        new_attrs = {}
        for attr_name, attr_value in attrs.items():
            if attr_name in "deserialize" and callable(attr_value):
                # Override the deserialize method with exception handling and logging
                new_attr_value = cls.wrap_method(attr_value)
            else:
                new_attr_value = attr_value
            new_attrs[attr_name] = new_attr_value
        return super().__new__(cls, name, bases, new_attrs)


class StringField(fields.String, metaclass=TrapExceptionsMeta):
    """Durable Stripping String Field."""

    @override
    def _deserialize(self, value, *_args, **_kwargs):
        if value in _STRING_EMPTY_VALUES:
            return ""

        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, int | float | Decimal):
            value = str(value)
        elif isinstance(value, str):
            value = value.encode("utf8", "replace")
        if isinstance(value, bytes):
            value = value.decode("utf8", "replace")
        if not isinstance(value, str):
            reason = f"{type(value)} is not a string"
            raise ValidationError(reason)
        return str(value).strip()


def half_replace(num):
    """Replace half notation with decimal notation."""
    return _HALF_RE.sub(".5", num)


class IssueField(StringField):
    """Issue Field."""

    @staticmethod
    def parse_issue(num):
        """Parse issues."""
        if not num:
            return ""
        num = num.replace(" ", "")
        num = num.lstrip("#")
        num = _LEADING_ZERO_RE.sub(r"\2", num)
        num = num.rstrip(".")
        return half_replace(num)

    @override
    def _deserialize(self, value, *args, **kwargs):
        value = super()._deserialize(value, *args, **kwargs)
        return self.parse_issue(value)
