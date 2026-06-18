"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.formats.comicbox.transform import ComicboxBaseTransform


class ComicboxYamlTransform(ComicboxBaseTransform):
    """Comicbox YAML transform."""

    SCHEMA_CLASS = ComicboxYamlSchema
