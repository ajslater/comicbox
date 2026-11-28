"""Custom Marshmallow fields."""

import re
import sys
from decimal import Decimal
from enum import Enum
from typing import Any

from marshmallow import fields
from marshmallow.exceptions import ValidationError

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


_STRING_EMPTY_VALUES = (None, "")
_LEADING_ZERO_RE = re.compile(r"^(0+)(\w)")
_HALF_RE = re.compile(r"(½|1/2)")
# A half where an issue's number goes: "½", "1/2", "5½", "5 1/2", "1/2 AU".
# Not "1/2/3", "11/2" or "1/23", which are other fractions, not halves.
_ISSUE_HALF_RE = re.compile(r"^(-?\d*)\s*(?:½|(?<!\d)1/2(?![/\d]))")
# Always matches: a leading number, possibly empty, then the rest.
# The leading number and the rest. A minus sign belongs to the number when a
# digit, or a point and a digit, follows it: issue -1 is a real issue number.
_SPLIT_ISSUE_RE = re.compile(r"((?:-(?=\.?\d))?\d*\.?\d*)(.*)")


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


def issue_half_replace(name: str, half: str = ".5") -> str:
    """Spell the half in an issue's number position as `half`."""
    return _ISSUE_HALF_RE.sub(rf"\g<1>{half}", name, count=1)


class IssueField(StringField):
    """Issue Field."""

    @staticmethod
    def parse_issue(num: str) -> str:
        """Parse issues."""
        if not num:
            return ""
        num = num.strip().lstrip("#")
        num = _LEADING_ZERO_RE.sub(r"\2", num)
        # Before the spaces go: "5 1/2" is a half, "51/2" is not.
        num = issue_half_replace(num)
        num = num.replace(" ", "")
        return num.rstrip(".")

    @staticmethod
    def split_issue(name: str) -> tuple[str, str]:
        """
        Split an issue name into its leading number and its suffix.

        ``-1AU`` is ``-1`` and ``AU``; a minus with no number after it, as in
        ``-AU``, is part of the suffix. A half is ``.5``: ``5 1/2`` and
        ``5½`` are ``5.5``, ``1/2 AU`` is ``.5`` and `` AU``.
        """
        match = _SPLIT_ISSUE_RE.match(issue_half_replace(name))
        if match is None:  # pragma: no cover - the pattern matches any string
            return "", name
        number, suffix = match.groups()
        return number, suffix

    @override
    def _deserialize(self, value: Any, *args: Any, **kwargs: Any) -> str:
        value = super()._deserialize(value, *args, **kwargs)
        return self.parse_issue(value)
