"""
ComicInfo GTIN <-> comicbox identifiers.

GTIN is a barcode: an ISBN, UPC, EAN or JAN. Other readers treat it as one,
so comicbox reads a single value and writes back only an identifier that
really is one. Comicbox's own database ids travel in the `Notes` urns and in
`Web` urls, which is where they belong and where comicbox reads them from.
"""

from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comic_info.schema import GTIN_TAG
from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY
from comicbox.identifiers import ID_KEY_KEY
from comicbox.identifiers.identifiers import create_identifier
from comicbox.identifiers.urns import parse_string_identifier

# A GTIN-13 or GTIN-14 barcode is all digits; an ISBN may carry hyphens and a
# trailing X check digit. Comicbox records the one it looks like.
_GTIN_ID_SOURCES = (IdSources.ISBN, IdSources.UPC, IdSources.GTIN)
_ISBN_LENGTHS = frozenset({10, 13})


def _gtin_id_source(gtin: str) -> str:
    """Name which kind of barcode this is."""
    digits = gtin.replace("-", "").replace(" ", "")
    if len(digits) in _ISBN_LENGTHS:
        return IdSources.ISBN.value
    return IdSources.UPC.value


def _urns_to_cb(gtin: str) -> dict:
    """
    Read urns an older comicbox wrote into GTIN, so those files still work.

    Comicbox used to dump every identifier here as a comma-joined list of
    urns. It no longer writes them, but plenty of files carry them.
    """
    identifiers = {}
    for part in gtin.split(","):
        candidate = part.strip()
        # Only a urn or a source-prefixed key qualifies, both of which carry a
        # colon. Without that guard a hyphenated ISBN reads as a ComicVine
        # long code.
        if not candidate or ":" not in candidate:
            continue
        id_source, id_type, id_key = parse_string_identifier(candidate, None)
        if not (id_source and id_key):
            continue
        if identifier := create_identifier(id_source.value, id_key, id_type=id_type):
            identifiers[id_source.value] = identifier
    return identifiers


def _to_cb(cix_gtin: Any) -> dict:
    """Read the GTIN as the barcode it is meant to be."""
    if not cix_gtin:
        return {}
    gtin = str(cix_gtin).strip()
    if not gtin:
        return {}
    if identifiers := _urns_to_cb(gtin):
        return identifiers
    id_source_str = _gtin_id_source(gtin)
    identifier = create_identifier(id_source_str, gtin)
    return {id_source_str: identifier} if identifier else {}


def _from_cb(comicbox_identifiers: dict[str, dict[str, str]]) -> str:
    """Write only a real barcode, never a database id."""
    for id_source in _GTIN_ID_SOURCES:
        identifier = comicbox_identifiers.get(id_source.value)
        if identifier and (id_key := identifier.get(ID_KEY_KEY)):
            return id_key
    return ""


COMICINFO_IDENTIFIERS_TO_CB = MetaSpec(key_map={IDENTIFIERS_KEY: GTIN_TAG}, spec=_to_cb)
COMICINFO_GTIN_FROM_CB = MetaSpec(key_map={GTIN_TAG: IDENTIFIERS_KEY}, spec=_from_cb)
