"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.formats.comicbox.schema.json_schema import ComicboxJsonSchema
from comicbox.formats.comicbox.transform import ComicboxBaseTransform


class ComicboxJsonTransform(ComicboxBaseTransform):
    """Comicbox JSON transform."""

    SCHEMA_CLASS = ComicboxJsonSchema
