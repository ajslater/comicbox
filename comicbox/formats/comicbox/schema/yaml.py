"""Comic yaml superclass."""

from marshmallow.fields import Nested

from comicbox.formats.base.schemas.yaml import YamlSchema, YamlSubSchema
from comicbox.formats.comicbox.schema import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)


class ComicboxYamlSubSchema(ComicboxSubSchemaMixin, YamlSubSchema):
    """YAML sub schema."""


class ComicboxYamlSchema(ComicboxSchemaMixin, YamlSchema):
    """YAML schema."""

    comicbox = Nested(ComicboxYamlSubSchema)
