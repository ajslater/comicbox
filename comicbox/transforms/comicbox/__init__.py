"""Comicbox JSON transform to and from Comicbox format."""

from types import MappingProxyType

from comicbox.schemas.comicbox import (
    APP_ID_KEY,
    COVER_DATE_KEY,
    DATE_KEY,
    DAY_KEY,
    ISSUE_KEY,
    MONTH_KEY,
    NAME_KEY,
    STORE_DATE_KEY,
    TAGGER_KEY,
    YEAR_KEY,
    ComicboxSchemaMixin,
)
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

ISSUE_NAME_KEYPATH = f"{ISSUE_KEY}.{NAME_KEY}"
COVER_DATE_KEYPATH = f"{DATE_KEY}.{COVER_DATE_KEY}"
STORE_DATE_KEYPATH = f"{DATE_KEY}.{STORE_DATE_KEY}"
YEAR_KEYPATH = f"{DATE_KEY}.{YEAR_KEY}"
MONTH_KEYPATH = f"{DATE_KEY}.{MONTH_KEY}"
DAY_KEYPATH = f"{DATE_KEY}.{DAY_KEY}"
_TAGGER_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{TAGGER_KEY}"

TOP_KEY_MAP = MappingProxyType(
    {
        APP_ID_KEY: _TAGGER_KEYPATH,
        ComicboxSchemaMixin.ROOT_KEYPATH: ComicboxSchemaMixin.ROOT_KEYPATH,
    }
)
METASPEC = MetaSpec(key_map=TOP_KEY_MAP, inherit_root_keypath=False)


class ComicboxBaseTransform(BaseTransform):
    """Comicbox YAML transform."""

    SPECS_TO = create_specs_to_comicbox(METASPEC)
    SPECS_FROM = create_specs_from_comicbox(METASPEC)
