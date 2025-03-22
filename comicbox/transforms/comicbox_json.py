"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_json import ComicboxJsonSchema
from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map


class ComicboxJsonTransform(JsonTransform):
    """Comicbox JSON transform."""

    SCHEMA_CLASS = ComicboxJsonSchema
    TOP_TAG_MAP = create_transform_map(
        KeyTransforms(key_map={APP_ID_KEY: TAGGER_KEY}), only_comicbox_root_tag=True
    )
