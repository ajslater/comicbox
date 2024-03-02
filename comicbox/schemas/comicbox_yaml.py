"""Comic yaml superclass."""

from marshmallow.fields import Nested

from comicbox.schemas.comicbox_mixin import ROOT_TAG, ComicboxSubSchemaMixin
from comicbox.schemas.yaml import YamlSchema, YamlSubSchema


class ComicboxYamlSubSchema(YamlSubSchema, ComicboxSubSchemaMixin):
    """YAML sub schema."""


class ComicboxYamlSchema(YamlSchema):
    """YAML schema."""

    FILENAME = "comicbox.yaml"
    CONFIG_KEYS = frozenset({"yaml"})
    ROOT_TAGS = (ROOT_TAG,)

    comicbox = Nested(ComicboxYamlSubSchema)
