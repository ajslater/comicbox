"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.comicbox import ComicboxBaseTransform


class ComicboxYamlTransform(ComicboxBaseTransform):
    """Comicbox YAML transform."""

    SCHEMA_CLASS = ComicboxYamlSchema
