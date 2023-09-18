"""Custom Marshmallow fields."""
import re
from logging import getLogger

from marshmallow import fields
from stringcase import titlecase

from comicfn2dict.regex import ORIGINAL_FORMAT_PATTERNS

LOG = getLogger(__name__)
_ORIGINAL_FORMAT_RE_EXP = r"^" + r"|".join(ORIGINAL_FORMAT_PATTERNS) + r"$"
_ORIGINAL_FORMAT_RE = re.compile(_ORIGINAL_FORMAT_RE_EXP, flags=re.IGNORECASE)
_CAPS_FORMATS = frozenset({"HC", "TPB"})
_PREFORMATTED_FORMATS = frozenset({"PDF Rip"})
_STRING_EMPTY_VALUES = (None, "")
EMPTY_VALUES = (*_STRING_EMPTY_VALUES, [], {})


class DeserializeMeta(type(fields.Field)):
    """Wrap the deserialize method to never throw."""

    @classmethod
    def wrap_deserialize(cls, deserialize_method):
        """Wrap deserialize method to never throw."""

        def wrapper(self, value, attr, *args, **kwargs):
            """Trap exceptions, log and return None."""
            try:
                return deserialize_method(self, value, attr, *args, **kwargs)
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
            if attr_name == "deserialize":
                # Override the deserialize method with exception handling and logging
                new_attrs[attr_name] = cls.wrap_deserialize(attr_value)
            else:
                new_attrs[attr_name] = attr_value
        return super().__new__(cls, name, bases, new_attrs)


class StringField(fields.String, metaclass=DeserializeMeta):
    """Durable Stripping String Field."""

    def _deserialize(self, value, *_args, **_kwargs):
        if value in _STRING_EMPTY_VALUES:
            return None

        if isinstance(value, str):
            value = value.encode("utf8", "replace")
        if isinstance(value, bytes):
            value = value.decode("utf8", "replace")
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
    def parse_issue(num):
        """Parse issues."""
        num = StringField().deserialize(num)
        if not num:
            return None
        num = num.replace(" ", "")
        num = num.lstrip("#")
        num = num.lstrip("0")
        num = num.rstrip(".")
        return half_replace(num)

    def _deserialize(self, value, *args, **kwargs):
        value = self.parse_issue(value)
        return super()._deserialize(value, *args, **kwargs)


class OriginalFormatField(StringField):
    """Prettify Original Format."""

    def _deserialize(self, value, *args, **kwargs):
        """Prettify Original Format if it's known."""
        value = super()._deserialize(value, *args, **kwargs)
        if not value or not _ORIGINAL_FORMAT_RE.search(value):
            return value
        value_upper = value.upper()
        for preformatted_value in _PREFORMATTED_FORMATS:
            if value_upper == preformatted_value.upper():
                value = preformatted_value
                break
        else:
            if value_upper in _CAPS_FORMATS:
                value = value_upper
            else:
                value = titlecase(value)
                value = value.replace("  ", " ")
        return value
