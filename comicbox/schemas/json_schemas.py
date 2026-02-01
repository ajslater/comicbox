"""Json Schema."""

from abc import ABC
from collections.abc import Mapping
from datetime import date, datetime
from types import MappingProxyType
from typing import Any

import simplejson as json
from typing_extensions import override

from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.schemas.base import BaseRenderModule, BaseSchema, BaseSubSchema


def datetime_handler(value):
    """Convert datetimes to strings for json.dumps."""
    if isinstance(value, date):
        value = DateField()._serialize(value, "", None)  # noqa: SLF001
    elif isinstance(value, datetime):
        value = DateTimeField()._serialize(value, "", None)  # noqa: SLF001
    return value


class JsonRenderModule(BaseRenderModule):
    """JSON Render module with custom formatting and Decimal support."""

    COMPACT_SEPARATORS = (",", ":")
    NORMAL_DUMPS_ARGS = MappingProxyType({"indent": 2})
    COMPACT_DUMPS_ARGS = MappingProxyType({"separators": COMPACT_SEPARATORS})

    @override
    @classmethod
    def dumps(cls, obj: Mapping, *args, compact=False, sort_keys=False, **kwargs):
        """Dump dict to JSON string with formatting."""
        extra_kwargs = cls.COMPACT_DUMPS_ARGS if compact else cls.NORMAL_DUMPS_ARGS
        return json.dumps(
            dict(obj),
            *args,
            sort_keys=sort_keys,
            iterable_as_array=True,
            use_decimal=True,
            default=datetime_handler,
            **extra_kwargs,
            **kwargs,
        )

    @override
    @classmethod
    def loads(cls, s: str | bytes | bytearray, *args, **kwargs) -> Any:
        """Load JSON string to dict."""
        if cleaned_s := cls.clean_string(s):
            return json.loads(
                cleaned_s,
                *args,
                use_decimal=True,
                **kwargs,
            )
        return None


class JsonSubSchema(BaseSubSchema, ABC):
    """Json Sub Schema."""


class JsonSchema(BaseSchema, ABC):
    """Json Schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = JsonRenderModule
