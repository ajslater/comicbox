"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox.json_schema import ComicboxJsonSchema
from comicbox.transforms.comicbox import ComicboxBaseTransform


class ComicboxJsonTransform(ComicboxBaseTransform):
    """Comicbox JSON transform."""

    SCHEMA_CLASS = ComicboxJsonSchema
