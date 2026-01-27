"""Json Schema."""

from abc import ABC
from typing import Any

import simplejson as json
from typing_extensions import override

from comicbox.schemas.base import BaseRenderModule, BaseSchema, BaseSubSchema


class JsonRenderModule(BaseRenderModule):
    """JSON Render module with custom formatting and Decimal support."""

    COMPACT_SEPARATORS = (",", ":")

    @override
    @classmethod
    def dumps(cls, obj: dict, *args, compact=False, **kwargs):
        """Dump dict to JSON string with formatting."""
        if compact:
            indent = None
            separators = cls.COMPACT_SEPARATORS
        else:
            indent = 2
            separators = None
        return json.dumps(
            obj,
            *args,
            indent=indent,
            iterable_as_array=True,
            separators=separators,
            sort_keys=False,
            use_decimal=True,
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
