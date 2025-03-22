"""Comicbox JSON transform to and from Comicbox format."""

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.transforms.yaml import YamlTransform


class ComicboxYamlTransform(YamlTransform):
    """Comicbox YAML transform."""

    SCHEMA_CLASS = ComicboxYamlSchema
    TOP_TAG_MAP = create_transform_map(
        KeyTransforms(key_map={APP_ID_KEY: TAGGER_KEY}), only_comicbox_root_tag=True
    )
