"""Marshmallow collection fields."""

import re
import sys
from collections.abc import Iterable, Mapping
from copy import deepcopy
from decimal import Decimal
from operator import itemgetter
from typing import Any

from glom import glom
from marshmallow import ValidationError, fields
from marshmallow.utils import is_collection

from comicbox.empty import filter_list_empty, is_empty
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.identifiers import ID_KEY_KEY
from comicbox.merge import AdditiveMerger

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

# Sort keys are compared element by element, so every element in a slot must be
# comparable with its siblings. Nothing guarantees they share a type: a reprint
# missing `volume.number` substitutes an empty value into a slot where its
# sibling holds an int, and `int < str` is a TypeError. Ranking the type first
# means unlike types are ordered by rank and never compared to each other.
_EMPTY_RANK = 0
_NUMBER_RANK = 1
_STRING_RANK = 2
_OTHER_RANK = 3
_NUMBER_TYPES = (int, float, Decimal)
# The comicbox schema's identifiers key. The schema package imports this
# module, so its constant would be a cycle.
_IDENTIFIERS_KEY = "identifiers"


def _comparable(value: Any) -> tuple[int, Any]:
    """Pair a sort key element with a rank for its comparability class."""
    if is_empty(value):
        # Absent and explicitly empty elements share a rank so they still
        # dedupe together, and sort first like the old empty string did.
        return (_EMPTY_RANK, "")
    if isinstance(value, str):
        return (_STRING_RANK, value)
    if isinstance(value, _NUMBER_TYPES):
        # Numbers stay numbers: 2 must keep sorting before 10.
        return (_NUMBER_RANK, value)
    # Dates, and anything else unhashable or unorderable against its own kind.
    return (_OTHER_RANK, str(value))


def _ids(element: Mapping) -> Mapping:
    ids = element.get(_IDENTIFIERS_KEY)
    return ids if isinstance(ids, Mapping) else {}


def _id_key(identifier: Any) -> Any:
    return identifier.get(ID_KEY_KEY) if isinstance(identifier, Mapping) else None


def _ids_conflict(left: Mapping, right: Mapping) -> bool:
    """
    Whether two elements hold different ids from one database.

    Two ids from one database name two things, however alike the rest of
    them reads. An id beside no id, or ids from different databases, say
    nothing about it.
    """
    left_ids, right_ids = _ids(left), _ids(right)
    for source in left_ids.keys() & right_ids.keys():
        left_key, right_key = _id_key(left_ids[source]), _id_key(right_ids[source])
        if left_key and right_key and left_key != right_key:
            return True
    return False


def _merge_elements(old: Mapping, new: Mapping) -> dict:
    """The later element wins its fields, but both sides' ids are kept."""
    merged = {**old, **new}
    if (old_ids := _ids(old)) and (new_ids := _ids(new)):
        merged[_IDENTIFIERS_KEY] = {**old_ids, **new_ids}
    return merged


def case_insensitive_dict(d: dict) -> dict:
    """
    Make a dict with string keys case insensitive.

    Keys that differ only in case name the same thing, such as one credited
    person spelled two ways by two sources. The later key wins, as it always
    has: sources merge highest precedence last, so the higher precedence
    source names it. When both values are mappings they are deep merged
    additively, so neither side's roles or ids are lost, and the later value
    wins a scalar both set. No DictField value schema holds a list, so the
    additive merge never extends one. Other values can't merge: the later
    value wins.
    """
    folded: dict[str, tuple[str, Any]] = {}
    for key, value in d.items():
        folded_key = key.lower()
        old = folded.get(folded_key)
        if old and isinstance(old[1], Mapping) and isinstance(value, Mapping):
            merged = AdditiveMerger.merge(deepcopy(dict(old[1])), value)
            folded[folded_key] = (key, merged)
        else:
            folded[folded_key] = (key, value)
    return dict(folded.values())


class ListField(fields.List):
    """List that guarauntees no empty values."""

    def __init__(
        self,
        *args: Any,
        # Sorting also does deduplication
        sort: bool = True,
        sort_keys: tuple[str, ...] | list[str] = (),
        fallback_sort_keys: tuple[str, ...] | list[str] = (),
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> None:
        """Add instance variables."""
        self._sort = sort
        # A tuple of dot delimited keys becomes a tuple of tuples.
        self._sort_keys = tuple(sort_keys)
        # Keys only for elements whose sort_keys are all empty, so elements
        # with no structured data don't all dedupe into one.
        self._fallback_sort_keys = tuple(fallback_sort_keys)
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

    def _key_values(self, value: Any, key_paths: tuple[str, ...]) -> list:
        key = []
        for key_path in key_paths:
            sort_value = glom(value, key_path, default=None)
            sort_value = self.get_tag_value(sort_value)
            key.append(_comparable(sort_value))
        return key

    def _sort_value(self, value: Any, sort_dict: dict[Any, Any]) -> None:
        if is_empty(value):
            return
        if self._sort_keys:
            key = self._key_values(value, self._sort_keys)
            if self._fallback_sort_keys and all(rank == _EMPTY_RANK for rank, _ in key):
                key += self._key_values(value, self._fallback_sort_keys)
        else:
            key = (_comparable(self.get_tag_value(value)),)
        key = tuple(key)

        # Combine elements that dedupe to the same key, unless their ids say
        # they are different things. Each key holds the distinct elements
        # that share it, in the order first seen. Merging builds a new dict
        # so the caller's data is never modified.
        group = sort_dict.setdefault(key, [])
        for index, old_value in enumerate(group):
            if not isinstance(old_value, Mapping) or not isinstance(value, Mapping):
                # Non mappings can't merge: the later element wins.
                group[index] = value
                return
            if not _ids_conflict(old_value, value):
                group[index] = _merge_elements(old_value, value)
                return
        group.append(value)

    def _sorted(self, values: list[Any]) -> list:
        """Create a dict of ordered keys to deduplicate and sort on."""
        if not self._sort:
            return values

        sort_dict: dict[tuple, list] = {}
        for value in values:
            self._sort_value(value, sort_dict)
        return [
            value
            for _key, group in sorted(sort_dict.items(), key=itemgetter(0))
            for value in group
        ]

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


class DictField(fields.Dict):
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


class StringListField(fields.List):
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

    @staticmethod
    def _seq_to_items(seq: Iterable[Any]) -> list[Any]:
        # A mapping or a nested collection is no name: the item field unwraps
        # an XML element's text or refuses it, instead of naming an item
        # after its repr.
        return [
            item if isinstance(item, Mapping) or is_collection(item) else str(item)
            for item in seq
            if not is_empty(item)
        ]

    @override
    def _deserialize(self, value: Any, *args: Any, **kwargs: Any) -> list[str | None]:
        """Deserialize CSV encodings of lists."""
        result = []
        if is_empty(value):
            return result
        if isinstance(value, bool):
            reason = f"{value!r} is not a list of names"
            raise ValidationError(reason)
        if isinstance(value, (*_NUMBER_TYPES, Mapping)):
            # A bare number is one name. A lone mapping is one item for the
            # item field to read or refuse.
            value = [value]
        # CSV encoding.
        if isinstance(value, str) and (value := StringField().deserialize(value)):
            value = self._split_regex.split(value)
        if not value:
            return result
        if not is_collection(value):
            reason = f"{type(value).__name__} is not a list of names"
            raise ValidationError(reason)
        # Already deserialized.
        value = self._seq_to_items(value)
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(  # pyright: ignore[reportIncompatibleMethodOverride]  # ty: ignore[incompatible-method-override]
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
    def _deserialize(self, *args: Any, **kwargs: Any) -> set[str | None] | str | None:  # pyright: ignore[reportIncompatibleMethodOverride], # ty: ignore[incompatible-method-override]
        """Cast to a set."""
        try:
            str_list = super()._deserialize(*args, **kwargs)
        except ValidationError as exc:
            # A partial load's valid_data is a list, not a set: drop the
            # field whole instead, as SimpleNamedDictField's union does.
            raise ValidationError(exc.messages) from exc
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
