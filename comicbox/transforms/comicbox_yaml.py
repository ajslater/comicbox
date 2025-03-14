"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.yaml import YamlTransform


class ComicboxYamlTransform(YamlTransform):
    """Comicbox YAML transform."""

    SCHEMA_CLASS = ComicboxYamlSchema
