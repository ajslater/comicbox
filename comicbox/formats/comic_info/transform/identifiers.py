"""Comicinfo Identifiers to Comicbox transform."""

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.transforms.identifiers import (
    identifiers_to_cb,
)
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comic_info.schema import GTIN_TAG
from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY


def _to_cb(cix_gtin: set[str] | None) -> dict:
    # ComicInfo GTINs are abused as identifiers pending a real identifier tag.
    return identifiers_to_cb(cix_gtin, naked_id_source=IdSources.ISBN.value)


COMICINFO_IDENTIFIERS_TO_CB = MetaSpec(key_map={IDENTIFIERS_KEY: GTIN_TAG}, spec=_to_cb)
