"""Marshmallow collection fields."""

import re
from collections.abc import Mapping
from typing import Any

from glom import glom
from marshmallow import fields
from marshmallow.utils import is_collection
from typing_extensions import override

from comicbox.empty import filter_list_empty, is_empty
from comicbox.fields.fields import (
    StringField,
    TrapExceptionsMeta,
)
from comicbox.fields.number_fields import IntegerField


def case_insensitive_dict(d: dict) -> dict:
    """Make a dict with string keys case insensitive."""
    cid = {k.lower(): (k, v) for k, v in d.items()}
    return {v[0]: v[1] for v in cid.values()}


class ListField(fields.List, metaclass=TrapExceptionsMeta):
    """List that guarauntees no empty values."""

    def __init__(
        self,
        *args,
        # Sorting also does deduplication
        sort: bool = True,
        sort_keys: tuple[str, ...] | list[str] = (),
        allow_empty: bool = False,
        **kwargs,
    ):
        """Add instance variables."""
        self._sort = sort
        # A tuple of dot delimited keys becomes a tuple of tuples.
        self._sort_keys = tuple(sort_keys)
        self._allow_empty = allow_empty
        super().__init__(*args, **kwargs)

    @override
    def _deserialize(self, value, *args, **kwargs):
        """Remove empty values."""
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        values = super()._deserialize(values, *args, **kwargs)
        if not self._allow_empty:
            values = list(filter_list_empty(values))
        if not values:
            return []
        return values

    @staticmethod
    def get_tag_value(value):
        """Override in XmlListField."""
        return value

    def _sorted(self, values) -> list:
        """Create a dict of ordered keys to deduplicate and sort on."""
        if not self._sort:
            return values

        # If dedupe ever needs to be decoupled, add an index to the key.
        sort_dict = {}
        for value in values:
            if is_empty(value):
                continue
            key = []
            if self._sort_keys:
                for key_path in self._sort_keys:
                    sort_value = glom(value, key_path, default=None)
                    sort_value = self.get_tag_value(sort_value)
                    sort_value = "" if sort_value is None else sort_value
                    key.append(sort_value)
            else:
                key = (self.get_tag_value(value),)
            key = tuple(key)

            # combine elements by key
            if isinstance(value, Mapping) and (old_value := sort_dict.get(key)):
                new_value = old_value.update(value)
            else:
                new_value = value

            sort_dict[key] = new_value

        return [item[1] for item in sorted(sort_dict.items())]

    @override
    def _serialize(self, value: Any, *args, **kwargs):
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        values = super()._serialize(values, *args, **kwargs)
        if not values:
            return []
        if not self._allow_empty:
            values = list(filter_list_empty(values))
        if not values:
            return []
        # Only sort on serialize
        return self._sorted(values)


class DictField(fields.Dict, metaclass=TrapExceptionsMeta):
    """Dict field for nested schemas with case insensitive keys and sorting."""

    def __init__(
        self,
        *args,
        keys: type[fields.Field] | fields.Field = StringField,
        case_insensitive=True,
        sort=True,
        allow_empty_keys=False,
        allow_empty_values=False,
        **kwargs,
    ):
        """Set flags."""
        self._case_insensitive = case_insensitive
        self._sort = sort
        self._allow_empty_keys = allow_empty_keys
        self._allow_empty_values = allow_empty_values
        super().__init__(*args, keys=keys, **kwargs)

    @override
    def _deserialize(self, data, *args, **kwargs):
        """Apply flag conditions."""
        result_dict = super()._deserialize(data, *args, **kwargs)
        result_dict.pop(None, None)
        if not self._allow_empty_keys:
            result_dict.pop("", None)
        if not self._allow_empty_values:
            result_dict = {k: v for k, v in result_dict.items() if not is_empty(v)}
        if self._case_insensitive:
            result_dict = case_insensitive_dict(result_dict)
        return result_dict

    @override
    def _serialize(self, data, *args, **kwargs):
        result_dict = super()._serialize(data, *args, **kwargs)
        if result_dict is None:
            return None
        result_dict.pop(None, None)
        if not self._allow_empty_keys:
            result_dict.pop("", None)
        if not self._allow_empty_values:
            result_dict = {k: v for k, v in result_dict.items() if not is_empty(v)}
        if self._case_insensitive:
            result_dict = case_insensitive_dict(result_dict)
        if self._sort:
            result_dict = dict(sorted(result_dict.items()))
        # Only sort on serialize
        return result_dict


class StringListField(fields.List, metaclass=TrapExceptionsMeta):
    """A list of non empty strings."""

    FIELD: fields.Field = StringField  # pyright: ignore[reportAssignmentType]
    DEFAULT_SEPARATORS: str = ",;"
    DEFAULT_SEPARATOR_RE: re.Pattern = re.compile(rf"[{DEFAULT_SEPARATORS}]")

    def __init__(self, *args, as_string=False, sort=True, separators="", **kwargs):
        """Initialize as a string list."""
        # The first character in separators is used to join on serialize
        super().__init__(self.FIELD, *args, **kwargs)
        self._as_string = as_string
        self._sort = sort
        if separators:
            re_exp = r"[" + separators + r"]"
            self._split_regex = re.compile(re_exp)
            self._join_separator = separators[0]
        else:
            self._split_regex = self.DEFAULT_SEPARATOR_RE
            self._join_separator = self.DEFAULT_SEPARATORS[0]

    @staticmethod
    def _seq_to_str_seq(seq) -> list[str]:
        return [str(item) for item in seq if not is_empty(item)]

    @override
    def _deserialize(self, value, *args, **kwargs) -> list[str] | None:  # pyright:ignore[reportIncompatibleMethodOverride]
        """Deserialize CSV encodings of lists."""
        if not value:
            return []
        # CSV encoding.
        if isinstance(value, str) and (value := StringField().deserialize(value)):
            value = self._split_regex.split(value)  # type: ignore[reportArgumentType]
        if value and is_collection(value):
            # Already deserialized.
            value = self._seq_to_str_seq(value)
            return super()._deserialize(value, *args, **kwargs)  # pyright: ignore[reportReturnType]
        return []

    @override
    def _serialize(self, value, *args, **kwargs) -> list[str] | str | None:  # pyright:ignore[reportIncompatibleMethodOverride]
        if not value:
            return None
        value = self._seq_to_str_seq(value)
        if self._sort:
            # Only sort on serialize
            value = sorted(value)
        if self._as_string:
            # For subclasses where items aren't always strings
            return self._join_separator.join(value)
        return super()._serialize(value, *args, **kwargs)


class StringSetField(StringListField):
    """A set of non-empty strings."""

    @override
    def _deserialize(self, *args, **kwargs) -> set[str] | str | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Cast to a set."""
        str_list = super()._deserialize(*args, **kwargs)
        if not str_list:
            return None
        return set(str_list)

    @override
    def _serialize(self, value, *args, **kwargs):
        if not value:
            return None
        value = set(value)
        return super()._serialize(value, *args, **kwargs)


class IntegerListField(StringListField):
    """A list of integers."""

    FIELD = IntegerField  # pyright: ignore[reportAssignmentType]

    def __init__(self, *args, sort: bool = False, **kwargs):
        """Use not sorting as the default."""
        super().__init__(*args, sort=sort, **kwargs)


class EmbeddedStringSetField(StringSetField):
    """Copy data to and from the special embedded field."""

    JSON_XML_START_CHARS = frozenset({"<", "{"})

    @classmethod
    def is_embedded_metadata(cls, value):
        """Return if this looks like a json or xml string."""
        return (
            isinstance(value, str)
            and (stripped_value := value.lstrip())
            and (stripped_value[0] in cls.JSON_XML_START_CHARS)
        )

    @override
    def _deserialize(self, value, attr, data, *args, **kwargs):  # type: ignore[reportIncompatibleMethodOverride]
        if self.is_embedded_metadata(value):
            return StringField().deserialize(value)
        return super()._deserialize(value, attr, data, *args, **kwargs)

    @override
    def _serialize(self, value, attr, obj, *args, **kwargs):  # type: ignore[reportIncompatibleMethodOverride]
        if not value:
            return None
        if self.is_embedded_metadata(value):
            return StringField()._serialize(value, attr, obj, *args, **kwargs)  # noqa: SLF001
        return super()._serialize(value, attr, obj, *args, **kwargs)
