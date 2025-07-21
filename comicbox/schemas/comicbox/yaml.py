"""Comic yaml superclass."""

from marshmallow.fields import Nested

from comicbox.schemas.comicbox import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)
from comicbox.schemas.yaml import YamlSchema, YamlSubSchema


class ComicboxYamlSubSchema(ComicboxSubSchemaMixin, YamlSubSchema):
    """YAML sub schema."""


class ComicboxYamlSchema(ComicboxSchemaMixin, YamlSchema):
    """YAML schema."""

    comicbox = Nested(ComicboxYamlSubSchema)
