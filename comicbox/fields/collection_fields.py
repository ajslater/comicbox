"""Marshmallow collection fields."""

import re
from collections.abc import Iterable
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
        *args: Any,
        # Sorting also does deduplication
        sort: bool = True,
        sort_keys: tuple[str, ...] | list[str] = (),
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> None:
        """Add instance variables."""
        self._sort = sort
        # A tuple of dot delimited keys becomes a tuple of tuples.
        self._sort_keys = tuple(sort_keys)
        self._allow_empty = allow_empty
        super().__init__(*args, **kwargs)

    @override
    def _deserialize(self, value: list[Any] | Any, *args: Any, **kwargs: Any) -> list:
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
    def get_tag_value(value: Any) -> Any:
        """Override in XmlListField."""
        return value

    def _sort_value(self, value: dict[str, Any], sort_dict: dict[Any, Any]) -> None:
        if is_empty(value):
            return
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
        if old_value := sort_dict.get(key):
            new_value = old_value.update(value)
        else:
            new_value = value

        sort_dict[key] = new_value

    def _sorted(self, values: list[dict[str, Any]]) -> list:
        """Create a dict of ordered keys to deduplicate and sort on."""
        if not self._sort:
            return values

        # If dedupe ever needs to be decoupled, add an index to the key.
        sort_dict = {}
        for value in values:
            self._sort_value(value, sort_dict)
        return [item[1] for item in sorted(sort_dict.items())]

    @override
    def _serialize(self, value: Any, *args: Any, **kwargs: Any) -> list | None:
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
        *args: Any,
        keys: type[fields.Field] | fields.Field = StringField,
        case_insensitive: bool = True,
        sort: bool = True,
        allow_empty_keys: bool = False,
        allow_empty_values: bool = False,
        **kwargs: Any,
    ) -> None:
        """Set flags."""
        self._case_insensitive = case_insensitive
        self._sort = sort
        self._allow_empty_keys = allow_empty_keys
        self._allow_empty_values = allow_empty_values
        super().__init__(*args, keys=keys, **kwargs)

    @override
    def _deserialize(self, *args: Any, **kwargs: Any) -> dict:
        """Apply flag conditions."""
        result_dict = super()._deserialize(*args, **kwargs)
        result_dict.pop(None, None)
        if not self._allow_empty_keys:
            result_dict.pop("", None)
        if not self._allow_empty_values:
            result_dict = {k: v for k, v in result_dict.items() if not is_empty(v)}
        if self._case_insensitive:
            result_dict = case_insensitive_dict(result_dict)
        return result_dict

    @override
    def _serialize(self, *args: Any, **kwargs: Any) -> dict | None:
        result_dict = super()._serialize(*args, **kwargs)
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

    FIELD: type[fields.Field] = StringField
    DEFAULT_SEPARATORS: str = ",;"
    DEFAULT_SEPARATOR_RE: re.Pattern = re.compile(rf"[{DEFAULT_SEPARATORS}]")

    def __init__(
        self,
        *args: Any,
        as_string: bool = False,
        sort: bool = True,
        separators: str = "",
        **kwargs: Any,
    ) -> None:
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
    def _seq_to_str_seq(seq: Iterable[Any]) -> list[str]:
        return [str(item) for item in seq if not is_empty(item)]

    @override
    def _deserialize(
        self, value: list[str] | set[str] | str, *args: Any, **kwargs: Any
    ) -> list[str | None]:
        """Deserialize CSV encodings of lists."""
        result = []
        if not value:
            return result
        # CSV encoding.
        if isinstance(value, str) and (value := StringField().deserialize(value)):
            value = self._split_regex.split(value)
        if value and is_collection(value):
            # Already deserialized.
            value = self._seq_to_str_seq(value)
            result = super()._deserialize(value, *args, **kwargs)
        return result

    @override
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self, value: set[str], *args: Any, **kwargs: Any
    ) -> list[str | None] | str | None:
        if not value:
            return None
        str_list = self._seq_to_str_seq(value)
        if self._sort:
            # Only sort on serialize
            str_list = sorted(str_list)
        if self._as_string:
            # For subclasses where items aren't always strings
            return self._join_separator.join(str_list)
        return super()._serialize(str_list, *args, **kwargs)


class StringSetField(StringListField):
    """A set of non-empty strings."""

    @override
    def _deserialize(self, *args: Any, **kwargs: Any) -> set[str | None] | str | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
        """Cast to a set."""
        str_list = super()._deserialize(*args, **kwargs)
        if not str_list:
            return None
        return set(str_list)

    @override
    def _serialize(
        self, value: set[str], *args: Any, **kwargs: Any
    ) -> list[str | None] | str | None:
        if not value:
            return None
        value = set(value)
        # could force this into a set as well, but may have implications for format serialization
        return super()._serialize(value, *args, **kwargs)


class IntegerListField(StringListField):
    """A list of integers."""

    FIELD = IntegerField

    def __init__(self, *args: Any, sort: bool = False, **kwargs: Any) -> None:
        """Use not sorting as the default."""
        super().__init__(*args, sort=sort, **kwargs)


class LegacyNestedMDStringSetField(StringSetField):
    """Copy data from the legacy special nested field."""

    JSON_XML_START_CHARS = frozenset({"<", "{"})

    @classmethod
    def is_nested_metadata(cls, value: Any) -> bool:
        """Return if this looks like a json or xml string."""
        return (
            isinstance(value, str)
            and bool(stripped_value := value.lstrip())
            and (stripped_value[0] in cls.JSON_XML_START_CHARS)
        )

    @override
    def _deserialize(  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[invalid-method-override]
        self,
        value: list[str] | str,
        attr: str,
        data: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> set[str | None] | list[str | None] | str | None:
        if self.is_nested_metadata(value):
            return StringField().deserialize(value)
        return super()._deserialize(value, attr, data, *args, **kwargs)
