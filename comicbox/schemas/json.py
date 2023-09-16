"""Json Schema."""
from types import MappingProxyType
from typing import Union

import simplejson as json

from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_base import ComicboxBaseSchema
from comicbox.version import VERSION


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
    def loads(s: Union[bytes, str], *args, **kwargs):
        """Load JSON string to dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            return json.loads(cleaned_s, *args, use_decimal=True, **kwargs)
        return None


class ComicboxJsonSchema(ComicboxBaseSchema):
    """Json Schema."""

    CONFIG_KEYS = frozenset({"cb", "comicbox", "json"})
    FILENAME = "comicbox.json"
    ROOT_TAG = "comicbox"
    ROOT_TAGS = MappingProxyType(
        {
            "appID": f"comicbox/{VERSION}",
            ROOT_TAG: {},
            "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json",
        }
    )

    class Meta(ComicboxBaseSchema.Meta):
        """Schema Options."""

        render_module = JsonRenderModule
