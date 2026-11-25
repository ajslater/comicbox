"""Comicbox Fields."""

import sys
from collections.abc import Mapping
from inspect import isclass
from typing import Any

from marshmallow.fields import Field, Nested
from marshmallow_union import Union

from comicbox.enums.maps.roles import COMICBOX_ROLE_ALIAS_MAP
from comicbox.formats.base.fields.collection_fields import (
    DictField,
    StringSetField,
)
from comicbox.formats.base.fields.enum_fields import (
    PrettifiedStringField,
)
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.formats.base.fields.union import UNION_SCHEMA_IGNORE_ERRORS
from comicbox.formats.base.schemas.base import BaseSubSchema
from comicbox.formats.comicbox.schema.identifiers import (
    IdentifiedNameSchema,
    IdentifiedSchema,
)
from comicbox.formats.comicbox.schema.pages import PageInfoSchema

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

NAME_KEY = "name"


class SimpleNamedDictField(Union):
    """A dict that also accepts a simple string set and builds a dict from that."""

    def __init__(
        self,
        *args: Any,
        keys: Field | type[Field] = StringField,
        values: Field | type[Field] | None = None,
        allow_empty_values: bool = True,
        sort: bool = True,
        **kwargs: Any,
    ) -> None:
        """Create the union."""
        if values is None:
            values = Nested(IdentifiedSchema)
        fields = [
            DictField(
                keys=keys,
                values=values,
                allow_empty_values=allow_empty_values,
                sort=sort,
            ),
            StringSetField(sort=sort),
        ]
        super().__init__(fields, *args, **kwargs)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]

    @override
    def _deserialize(
        self,
        value: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict:
        result: dict = super()._deserialize(value, *args, **kwargs)
        if isinstance(result, set | frozenset):
            dict_value = {}
            for key in result:
                dict_value[key] = {}
            result = dict(super()._deserialize(dict_value, *args, **kwargs))
        return result


class SimpleNamedNestedField(Union):
    """
    A nested schema that also reads a plain name or number.

    ``series: Crimson Tide`` is read as ``series: {name: Crimson Tide}``, and
    ``volume: 2006`` as ``volume: {number: 2006}``.
    """

    def __init__(
        self,
        *args: Any,
        schema: type[BaseSubSchema] = IdentifiedNameSchema,
        field: Field | type[Field] = StringField,
        name_key: str = NAME_KEY,
        **kwargs: Any,
    ) -> None:
        """Create the union."""
        self._name_key = name_key
        if isclass(field):
            field = field()
        self._plain_field: Field = field
        fields = [Nested(schema(ignore_errors=UNION_SCHEMA_IGNORE_ERRORS)), field]
        super().__init__(fields, *args, **kwargs)

    @override
    def _deserialize(
        self,
        value: Any,
        attr: str | None = None,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict:
        if not isinstance(value, Mapping):
            # The nested schema reads a value that is not a mapping as empty,
            # without an error, so the union never reached the plain field
            # and a plain name was dropped unlogged. Read it here: an invalid
            # one raises, and its schema logs the drop.
            plain = self._plain_field.deserialize(value, attr, data, **kwargs)
            value = {self._name_key: plain}
        return super()._deserialize(value, attr, data, **kwargs)


class RoleField(PrettifiedStringField):
    """Prettified Role Field."""

    ENUM_ALIAS_MAP = COMICBOX_ROLE_ALIAS_MAP


class PagesField(DictField):  # CIX ONLY, CT
    """ComicInfo Pages."""

    def __init__(self, *args: Any, keys_as_string: bool = False, **kwargs: Any) -> None:
        """ComicInfo Pages with keys_as_string option."""
        super().__init__(
            *args,
            keys=IntegerField(minimum=0, as_string=keys_as_string),
            values=Nested(PageInfoSchema),
            case_insensitive=False,
            **kwargs,
        )
