"""Comicbox Fields."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime

    import ruamel.yaml

from inspect import isclass

from marshmallow.fields import Field, Nested
from marshmallow_union import Union
from typing_extensions import override

from comicbox.enums.maps.roles import COMICBOX_ROLE_ALIAS_MAP
from comicbox.fields.collection_fields import (
    DictField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
    PrettifiedStringField,
)
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.union import UNION_SCHEMA_IGNORE_ERRORS
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.comicbox.identifiers import (
    IdentifiedNameSchema,
    IdentifiedSchema,
)
from comicbox.schemas.comicbox.pages import PageInfoSchema

NAME_KEY = "name"


class SimpleNamedDictField(Union):
    """A dict that also accepts a simple string set and builds a dict from that."""

    def __init__(
        self: Any,
        *args: None,
        keys: Field | type[Field] = StringField,
        values: Field | type[Field] | None = None,
        allow_empty_values: bool = True,
        sort: bool = True,
        **kwargs: None,
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
    def _deserialize(self: Any, value: "dict[str, dict[str, dict[str, dict[Any, Any]]]]|dict[str, dict[str, int]]|dict[str, dict[Any, Any]]|dict[Any, Any]|ruamel.yaml.CommentedMap", *args: "dict[str, None]|dict[str, datetime.datetime]|dict[str, dict[str, None]]|dict[str, dict[str, dict[str, dict[str, dict[Any, Any]]]]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, str]|ruamel.yaml.CommentedMap|str", **kwargs: bool) -> dict:
        result: dict = super()._deserialize(value, *args, **kwargs)
        if isinstance(result, set | frozenset):
            dict_value = {}
            for key in result:
                dict_value[key] = {}
            result = dict(super()._deserialize(dict_value, *args, **kwargs))
        return result


class SimpleNamedNestedField(Union):
    """Return a union of a nested schema and an alternate field."""

    def __init__(
        self: Any,
        *args: None,
        schema: type[BaseSubSchema] = IdentifiedNameSchema,
        field: Field | type[Field] = StringField,
        name_key: str = NAME_KEY,
        primitive_type: type = str,
        **kwargs: None,
    ) -> None:
        """Create the union."""
        self._name_key = name_key
        self._primitive_type = primitive_type
        if isclass(field):
            field = field()
        fields = [Nested(schema(ignore_errors=UNION_SCHEMA_IGNORE_ERRORS)), field]
        super().__init__(fields, *args, **kwargs)

    @override
    def _deserialize(self: Any, value: "dict[str, None]|dict[str, str]|ruamel.yaml.CommentedMap", *args: "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, str]|ruamel.yaml.CommentedMap|str", **kwargs: bool) -> dict:
        result = super()._deserialize(value, *args, **kwargs)
        if isinstance(result, self._primitive_type):
            complex_value = {self._name_key: result}
            result = super()._deserialize(complex_value, *args, **kwargs)
        return result


class RoleField(PrettifiedStringField):
    """Prettified Role Field."""

    ENUM_ALIAS_MAP = COMICBOX_ROLE_ALIAS_MAP


class PagesField(DictField):  # CIX ONLY, CT
    """ComicInfo Pages."""

    def __init__(self: Any, *args: None, keys_as_string: bool=False, **kwargs: None) -> None:
        """ComicInfo Pages with keys_as_string option."""
        super().__init__(
            *args,
            keys=IntegerField(minimum=0, as_string=keys_as_string),
            values=Nested(PageInfoSchema),
            case_insensitive=False,
            **kwargs,
        )
