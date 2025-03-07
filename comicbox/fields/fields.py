"""Custom Marshmallow fields."""

from abc import ABCMeta
from decimal import Decimal
from logging import getLogger

from marshmallow import fields
from marshmallow.exceptions import ValidationError

LOG = getLogger(__name__)
_STRING_EMPTY_VALUES = (None, "")
EMPTY_VALUES = (*_STRING_EMPTY_VALUES, [], {})


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
                LOG.warning(
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

    def _deserialize(self, value, *_args, **_kwargs):
        if value in _STRING_EMPTY_VALUES:
            return None

        if isinstance(value, str):
            value = value.encode("utf8", "replace")
        if isinstance(value, bytes):
            value = value.decode("utf8", "replace")
        if not isinstance(value, str):
            reason = f"{type(value)} is not a string"
            raise ValidationError(reason)
        value = str(value).strip()
        if not value:
            return None
        return value


def half_replace(num_str):
    """Replace half notation with decimal notation."""
    num_str = num_str.replace("½", ".5", 1)
    return num_str.replace("1/2", ".5", 1)


class IssueField(StringField):
    """Issue Field."""

    @staticmethod
    def parse_issue(num_obj):
        """Parse issues."""
        num: str | None = StringField().deserialize(num_obj)  # type: ignore[reportAssignmentType]
        if not num:
            return None
        num = num.replace(" ", "")
        num = num.lstrip("#")
        num = num.lstrip("0")
        num = num.rstrip(".")
        return half_replace(num)

    def _deserialize(self, value, *args, **kwargs):
        if isinstance(value, int | float | Decimal):
            value = str(value)
        value = super()._deserialize(value, *args, **kwargs)
        return self.parse_issue(value)
