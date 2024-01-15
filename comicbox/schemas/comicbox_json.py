"""Json Schema."""
from marshmallow.fields import Constant, Nested

from comicbox.schemas.comicbox_mixin import ROOT_TAG, ComicboxSchemaMixin
from comicbox.schemas.json import JsonSchema, JsonSubSchema
from comicbox.version import VERSION


class ComicboxJsonSubSchema(JsonSubSchema, ComicboxSchemaMixin):
    """Json Sub Schema."""


class ComicboxJsonSchema(JsonSchema):
    """Json Schema."""

    CONFIG_KEYS = frozenset({"cb", "comicbox", "json"})
    FILENAME = "comicbox.json"
    ROOT_TAGS = (ROOT_TAG,)

    appID = Constant(f"comicbox/{VERSION}")  # noqa: N815
    comicbox = Nested(ComicboxJsonSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json"
    )
