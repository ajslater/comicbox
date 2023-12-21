"""Marshmallow collection fields."""
import re
from typing import Any, Union

from marshmallow import fields
from marshmallow.utils import is_collection

from comicbox.fields.fields import (
    EMPTY_VALUES,
    DeserializeMeta,
    StringField,
)
from comicbox.fields.numbers import IntegerField
from comicbox.schemas.identifier import IdentifierSchema


class ListField(fields.List, metaclass=DeserializeMeta):
    """List that guarauntees no empty values."""

    @staticmethod
    def _is_not_empty(value):
        return value not in EMPTY_VALUES

    def _deserialize(self, *args, **kwargs):
        """Remove empty values."""
        value = args[0]
        value = super()._deserialize(*args, **kwargs)
        value = list(filter(self._is_not_empty, value))
        if value:
            return value
        return []


class DictStringField(fields.Dict, metaclass=DeserializeMeta):
    """Dict that guarauntees no empty keys."""

    def __init__(self, *args, **kwargs):
        """Set up String Keys."""
        super().__init__(*args, keys=StringField(), **kwargs)

    def _deserialize(self, *args, **kwargs):
        """Remove empty key."""
        result_dict = super()._deserialize(*args, **kwargs)
        result_dict.pop(None, None)
        if result_dict:
            return result_dict
        return {}


class StringListField(fields.List, metaclass=DeserializeMeta):
    """A list of non empty strings."""

    FIELD = StringField
    STR_LIST_RE = re.compile(r"[,;]")

    def __init__(self, *args, as_string=False, sort=True, **kwargs):
        """Initialize as a string list."""
        super().__init__(self.FIELD, *args, **kwargs)
        self._as_string = as_string
        self._sort = sort

    def _deserialize(self, value, *args, **kwargs):
        """Deserialize CSV encodings of lists."""
        if not value:
            return []
        if isinstance(value, str):
            # CSV encoding.
            value = StringField().deserialize(value)
            if value:
                value = self.STR_LIST_RE.split(value)
        if value and is_collection(value):
            # Already deserialized.
            value = ("" if item is None else item for item in value)
            return super()._deserialize(value, *args, **kwargs)
        return []

    def _serialize(self, value, *args, **kwargs) -> Union[list[Any], str, None]:  # type:ignore
        if self._sort:
            value = sorted(value)
        if self._as_string:
            # For subclasses where items aren't always strings
            string_value = (str(item) for item in value)
            return ",".join(string_value)
        return super()._serialize(value, *args, **kwargs)


class StringSetField(StringListField):
    """A set of non-empty strings."""

    def _deserialize(self, *args, **kwargs) -> Union[set[Any], str, None]:  # type: ignore
        """Cast to a set."""
        str_list = super()._deserialize(*args, **kwargs)
        if not str_list:
            return None
        return set(str_list)


class IntegerListField(StringListField):
    """A list of integers."""

    FIELD = IntegerField


class IdentifiersField(DictStringField):
    """Dict of identifiers keyed by namespaces."""

    def __init__(self, *args, **kwargs):
        """Set up Identifier Values."""
        super().__init__(*args, values=fields.Nested(IdentifierSchema), **kwargs)
