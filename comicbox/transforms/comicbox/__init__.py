"""Comicbox JSON transform to and from Comicbox format."""

from types import MappingProxyType

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY, ComicboxSchemaMixin
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

TAGGER_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{TAGGER_KEY}"

TOP_KEY_MAP = MappingProxyType(
    {
        APP_ID_KEY: TAGGER_KEY_PATH,
        ComicboxSchemaMixin.ROOT_KEY_PATH: ComicboxSchemaMixin.ROOT_KEY_PATH,
    }
)
METASPEC = MetaSpec(key_map=TOP_KEY_MAP, inherit_root_keypath=False)


class ComicboxBaseTransform(BaseTransform):
    """Comicbox YAML transform."""

    SPECS_TO = create_specs_to_comicbox(METASPEC)
    SPECS_FROM = create_specs_from_comicbox(METASPEC)
