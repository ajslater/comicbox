"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY, ComicboxSchemaMixin
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map

TAGGER_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{TAGGER_KEY}"


class ComicboxBaseTransform(BaseTransform):
    """Comicbox YAML transform."""

    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                APP_ID_KEY: TAGGER_KEY_PATH,
                ComicboxSchemaMixin.ROOT_KEY_PATH: ComicboxSchemaMixin.ROOT_KEY_PATH,
            },
            inherit_root_key_path=False,
        )
    )
