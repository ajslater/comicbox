"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map


class ComicboxBaseTransform(BaseTransform):
    """Comicbox YAML transform."""

    TOP_TAG_MAP = create_transform_map(
        KeyTransforms(key_map={APP_ID_KEY: TAGGER_KEY}), only_comicbox_root_tag=True
    )
