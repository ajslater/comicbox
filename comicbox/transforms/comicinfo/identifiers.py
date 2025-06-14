"""Comicinfo Identifiers to Comicbox transform."""

from comicbox.identifiers import IdSources
from comicbox.merge import AdditiveMerger
from comicbox.schemas.comicbox import IDENTIFIERS_KEY
from comicbox.schemas.comicinfo import GTIN_TAG, WEB_TAG
from comicbox.transforms.identifiers import (
    identifiers_to_cb,
    urls_to_cb,
)
from comicbox.transforms.spec import MetaSpec


def _to_cb(values):
    # ComicInfo GTINs are abused as identifiers pending a real identifier tag.
    cix_gtin = values.get(GTIN_TAG)
    comicbox_identifiers = identifiers_to_cb(
        cix_gtin, naked_id_source=IdSources.ISBN.value
    )

    cix_web = values.get(WEB_TAG)
    comicbox_web_identifiers = urls_to_cb(cix_web)

    AdditiveMerger.merge(comicbox_identifiers, comicbox_web_identifiers)
    return comicbox_identifiers


COMICINFO_IDENTIFIERS_TO_CB = MetaSpec(
    key_map={IDENTIFIERS_KEY: (WEB_TAG, GTIN_TAG)}, spec=_to_cb
)
