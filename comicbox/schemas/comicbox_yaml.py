"""Comic yaml superclass."""
from marshmallow.fields import Nested

from comicbox.schemas.comicbox_mixin import ROOT_TAG, ComicboxSchemaMixin
from comicbox.schemas.yaml import YamlSchema, YamlSubSchema


class ComicboxYamlSubSchema(YamlSubSchema, ComicboxSchemaMixin):
    """YAML sub schema."""


class ComicboxYamlSchema(YamlSchema, ComicboxSchemaMixin):
    """YAML schema."""

    FILENAME = "comicbox.yaml"
    CONFIG_KEYS = frozenset({"yaml"})
    ROOT_TAGS = (ROOT_TAG,)

    comicbox = Nested(ComicboxYamlSubSchema)
