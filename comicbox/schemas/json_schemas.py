"""Json Schema."""

from abc import ABC

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
            indent=indent,  # ty: ignore[parameter-already-assigned]
            iterable_as_array=True,  # ty: ignore[parameter-already-assigned]
            separators=separators,  # ty: ignore[parameter-already-assigned]
            sort_keys=False,  # ty: ignore[parameter-already-assigned]
            use_decimal=True,  # ty: ignore[parameter-already-assigned]
            **kwargs,
        )

    @override
    @classmethod
    def loads(cls, s: bytes | str, *args, **kwargs):
        """Load JSON string to dict."""
        if cleaned_s := cls.clean_string(s):
            return json.loads(
                cleaned_s,
                *args,
                use_decimal=True,  # ty: ignore[parameter-already-assigned]
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
