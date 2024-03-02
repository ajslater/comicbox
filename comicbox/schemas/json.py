"""Json Schema."""

from abc import ABC

import simplejson as json

from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSchema, BaseSubSchema


class JsonRenderModule:
    """JSON Render module with custom formatting and Decimal support."""

    @staticmethod
    def dumps(obj: dict, *args, compact=False, **kwargs):
        """Dump dict to JSON string with formatting."""
        if compact:
            indent = None
            separators = (",", ":")
        else:
            indent = 2
            separators = None
        return json.dumps(
            obj,
            *args,
            indent=indent,
            iterable_as_array=True,
            separators=separators,
            sort_keys=True,
            use_decimal=True,
            **kwargs,
        )

    @staticmethod
    def loads(s: bytes | str, *args, **kwargs):
        """Load JSON string to dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            return json.loads(cleaned_s, *args, use_decimal=True, **kwargs)
        return None


class JsonSubSchema(BaseSubSchema, ABC):
    """Json Sub Schema."""


class JsonSchema(BaseSchema, ABC):
    """Json Schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = JsonRenderModule
