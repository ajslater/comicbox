"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.comicbox_mixin import ComicboxTransformMixin
from comicbox.transforms.yaml import YamlTransform


class ComicboxYamlTransform(YamlTransform, ComicboxTransformMixin):
    """Comicbox YAML transform."""

    SCHEMA_CLASS = ComicboxYamlSchema
