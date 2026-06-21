"""Comicinfo Identifiers to Comicbox transform."""

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.transforms.identifiers import (
    identifiers_to_cb,
    merge_url_and_explicit_identifiers,
    urls_to_cb,
)
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comic_info.schema import GTIN_TAG, WEB_TAG
from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY


def _to_cb(values: dict[str, set[str] | None]) -> dict:
    # ComicInfo GTINs are abused as identifiers pending a real identifier tag.
    cix_gtin = values.get(GTIN_TAG)
    comicbox_identifiers = identifiers_to_cb(
        cix_gtin, naked_id_source=IdSources.ISBN.value
    )

    cix_web = values.get(WEB_TAG)
    comicbox_web_identifiers = urls_to_cb(cix_web)

    # GTIN ids are authoritative; a <Web> URL slug must not clobber them.
    return merge_url_and_explicit_identifiers(
        comicbox_web_identifiers, comicbox_identifiers
    )


COMICINFO_IDENTIFIERS_TO_CB = MetaSpec(
    key_map={IDENTIFIERS_KEY: (WEB_TAG, GTIN_TAG)}, spec=_to_cb
)
