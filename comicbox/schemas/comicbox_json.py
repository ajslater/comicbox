"""Json Schema."""

from marshmallow.fields import Constant, Nested

from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_mixin import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema


class ComicboxJsonSubSchema(JsonSubSchema, ComicboxSubSchemaMixin):
    """Json Sub Schema."""


class ComicboxJsonSchema(ComicboxSchemaMixin, JsonSchema):
    """Json Schema."""

    TAG_ORDER = ("appID", ComicboxSchemaMixin.ROOT_TAG, "schema")

    appID = StringField()  # noqa: N815
    comicbox = Nested(ComicboxJsonSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json"
    )
