"""Json Schema."""

from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import DictField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.schemas.comicbox import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
    PageInfoSchema,
)
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema


class ComicboxJsonSubSchema(JsonSubSchema, ComicboxSubSchemaMixin):
    """Json Sub Schema."""

    pages = DictField(
        keys=IntegerField(minimum=0, as_string=True),
        values=Nested(PageInfoSchema),
        case_insensitive=False,
    )


class ComicboxJsonSchema(ComicboxSchemaMixin, JsonSchema):
    """Json Schema."""

    TAG_ORDER = ("appID", ComicboxSchemaMixin.ROOT_TAG, "schema")

    appID = StringField()  # noqa: N815
    comicbox = Nested(ComicboxJsonSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json"
    )
