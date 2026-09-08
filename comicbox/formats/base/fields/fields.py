"""Custom Marshmallow fields."""

import re
from decimal import Decimal
from enum import Enum
from typing import Any

from marshmallow import fields
from marshmallow.exceptions import ValidationError
from typing_extensions import override

_STRING_EMPTY_VALUES = (None, "")
_LEADING_ZERO_RE = re.compile(r"^(0+)(\w)")
_HALF_RE = re.compile(r"(½|1/2)")


class StringField(fields.String):
    """Durable Stripping String Field."""

    def __init__(self, *args: Any, clean_tabs: bool = False, **kwargs: Any) -> None:
        """Add a clean tabs flag."""
        self.clean_tabs = clean_tabs
        super().__init__(*args, **kwargs)

    @override
    def _deserialize(
        self, value: str | float | Decimal | Enum, *_args: Any, **_kwargs: Any
    ) -> str:
        if value in _STRING_EMPTY_VALUES:
            return ""

        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, int | float | Decimal):
            value = str(value)
        elif isinstance(value, str):
            value_bytes: bytes = value.encode("utf8", "replace")
            value = value_bytes.decode("utf8", "replace")
            if self.clean_tabs:
                value = value.replace("\t", " ")
        elif isinstance(value, bytearray | bytes):
            value = bytes(value).decode("utf8", "replace")
            if self.clean_tabs:
                value = value.replace("\t", " ")
        if not isinstance(value, str):
            reason = f"{type(value)} is not a string"
            raise ValidationError(reason)
        return str(value).strip()


def half_replace(num: str) -> str:
    """Replace half notation with decimal notation."""
    return _HALF_RE.sub(".5", num)


class IssueField(StringField):
    """Issue Field."""

    @staticmethod
    def parse_issue(num: str) -> str:
        """Parse issues."""
        if not num:
            return ""
        num = num.replace(" ", "")
        num = num.lstrip("#")
        num = _LEADING_ZERO_RE.sub(r"\2", num)
        num = num.rstrip(".")
        return half_replace(num)

    @override
    def _deserialize(self, value: str, *args: Any, **kwargs: Any) -> str:
        value = super()._deserialize(value, *args, **kwargs)
        return self.parse_issue(value)
