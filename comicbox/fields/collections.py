"""Marshmallow collection fields."""
import re
from collections.abc import Mapping, Sequence

from marshmallow import fields
from marshmallow.utils import is_collection
from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.fields.fields import (
    EMPTY_VALUES,
    DeserializeMeta,
    StringField,
)
from comicbox.identifiers import (
    coerce_urn_nid,
    parse_identifier_str,
    parse_urn_identifier,
)


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
        return None


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
        return None


class StringListField(fields.List, metaclass=DeserializeMeta):
    """A list of non empty strings."""

    STR_LIST_RE = re.compile(r"[,;]")

    def __init__(self, *args, as_string=False, sort=True, **kwargs):
        """Initialize as a string list."""
        super().__init__(StringField, *args, **kwargs)
        self._as_string = as_string
        self._sort = sort

    def _deserialize(self, value, *args, **kwargs):
        """Deserialize CSV encodings of lists."""
        if not value:
            return None
        if isinstance(value, str):
            # CSV encoding.
            value = StringField().deserialize(value)
            if value:
                value = self.STR_LIST_RE.split(value)
        if value and is_collection(value):
            # Already deserialized.
            value = filter(None, value)
            return super()._deserialize(value, *args, **kwargs)
        return None

    def _serialize(self, value, *args, **kwargs):
        value = list(filter(None, value))
        if self._sort:
            value = sorted(value)
        if self._as_string:
            return ",".join(value)  # type: ignore
        return super()._serialize(value, *args, **kwargs)


class StringSetField(StringListField):
    """A set of non-empty strings."""

    def _deserialize(self, *args, **kwargs):
        """Cast to a set."""
        str_list = super()._deserialize(*args, **kwargs)
        if not str_list:
            return None
        return set(str_list)


class IdentifiersField(fields.Dict, metaclass=DeserializeMeta):
    """Identifiers field."""

    def __init__(
        self, *args, as_string_order=None, naked_identifier_type=None, **kwargs
    ):
        """Set up Dict."""
        self._as_string_order = as_string_order
        self._naked_identifier_type = naked_identifier_type
        super().__init__(*args, keys=StringField(), values=StringField(), **kwargs)

    def _deserialize(self, value, *args, **kwargs):
        if isinstance(value, str):
            value = value.split(",;")
        if isinstance(value, (Sequence, set, frozenset)):
            # Allow multiple identifiers from xml, etc.
            # Technically out of spec.
            new_value = {}
            for item in value:
                identifier_type, code = parse_urn_identifier(item)
                if not code:
                    identifier_type, code = parse_identifier_str(item)
                if self._naked_identifier_type and not identifier_type:
                    identifier_type = self._naked_identifier_type
                new_value[identifier_type] = code
            value = new_value
        if isinstance(value, Mapping):
            coerced_items = {}
            for identifier_type, code in value.items():
                coerced_identifier_type = coerce_urn_nid(identifier_type)
                coerced_items[coerced_identifier_type] = code
            value = coerced_items
        return super()._deserialize(value, *args, **kwargs)

    @staticmethod
    def to_urn_string(nid_str, nss_str):
        """Compose an urn string."""
        nid = NSIdentifier(nid_str)
        nss = NSSString(nss_str)
        urn = URN8141(nid=nid, nss=nss)
        return str(urn)

    def _serialize(self, value, *args, **kwargs):
        if self._as_string_order:
            if not value:
                return None
            # Order important
            for identifier_type in self._as_string_order:
                code = value.get(identifier_type)
                if code:
                    break
            else:
                return None
            if (
                self._naked_identifier_type
                and identifier_type == self._naked_identifier_type
            ):
                return code
            return self.to_urn_string(identifier_type, code)
        return super()._serialize(value, *args, **kwargs)
