"""Json Schema."""

from math import ceil, log10

from marshmallow.fields import Constant, Nested
from typing_extensions import override

from comicbox.fields.comicbox import PagesField
from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox import (
    PAGES_KEY,
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema


class ComicboxJsonSubSchema(JsonSubSchema, ComicboxSubSchemaMixin):
    """Json Sub Schema."""

    # Key must be strings in json.
    pages = PagesField(keys_as_string=True)


class ComicboxJsonSchema(ComicboxSchemaMixin, JsonSchema):
    """Json Schema."""

    TAG_ORDER: tuple[str, ...] = ("appID", ComicboxSchemaMixin.ROOT_TAG, "schema")

    appID = StringField()  # noqa: N815
    comicbox = Nested(ComicboxJsonSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json"
    )

    @override
    def dump(self, obj: dict, *args, **kwargs):
        """Inject zero fill for page string numbers."""
        if obj and (pages := obj.get(self.ROOT_TAG, {}).get(PAGES_KEY)):
            comicbox_field = self.fields[self.ROOT_TAG].schema  # pyright: ignore[reportAttributeAccessIssue]
            pages_field = comicbox_field.fields[PAGES_KEY]
            max_page = max(*pages.keys(), 0)
            zero_fill = ceil(log10(max_page))
            pages_field.key_field.ZERO_FILL = zero_fill
        return super().dump(obj, *args, **kwargs)
