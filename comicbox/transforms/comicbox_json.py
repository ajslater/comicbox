"""Comicbox JSON transform to and from Comicbox format."""

from bidict import frozenbidict

from comicbox.schemas.comicbox_json import ComicboxJsonSchema
from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY
from comicbox.transforms.json_transforms import JsonTransform


class ComicboxJsonTransform(JsonTransform):
    """Comicbox JSON transform."""

    SCHEMA_CLASS = ComicboxJsonSchema
    TOP_TAG_MAP = frozenbidict({(APP_ID_KEY, None): (TAGGER_KEY, None)})
