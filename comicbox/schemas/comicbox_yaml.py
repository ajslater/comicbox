"""Comic yaml superclass."""

from marshmallow.fields import Nested

from comicbox.schemas.comicbox_mixin import (
    ComicboxSchemaMixin,
    ComicboxSubSchemaMixin,
)
from comicbox.schemas.yaml import YamlSchema, YamlSubSchema


class ComicboxYamlSubSchema(YamlSubSchema, ComicboxSubSchemaMixin):
    """YAML sub schema."""


class ComicboxYamlSchema(ComicboxSchemaMixin, YamlSchema):
    """YAML schema."""

    FILENAME = "comicbox.yaml"
    CONFIG_KEYS = frozenset({"yaml"})

    comicbox = Nested(ComicboxYamlSubSchema)
