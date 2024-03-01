"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_json import ComicboxJsonSchema
from comicbox.transforms.comicbox_mixin import ComicboxTransformMixin
from comicbox.transforms.json import JsonTransform


class ComicboxJsonTransform(JsonTransform, ComicboxTransformMixin):
    """Comicbox JSON transform."""

    SCHEMA_CLASS = ComicboxJsonSchema
