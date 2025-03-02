"""Json Schema."""

from marshmallow.fields import Constant, Nested

from comicbox.schemas.comicbox_mixin import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema
from comicbox.version import VERSION


class ComicboxJsonSubSchema(JsonSubSchema, ComicboxSubSchemaMixin):
    """Json Sub Schema."""


class ComicboxJsonSchema(ComicboxSchemaMixin, JsonSchema):
    """Json Schema."""

    CONFIG_KEYS = frozenset({"cb", "comicbox", "json"})
    FILENAME = "comicbox.json"

    appID = Constant(f"comicbox/{VERSION}")  # noqa: N815
    comicbox = Nested(ComicboxJsonSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json"
    )
