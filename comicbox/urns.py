"""Universal Resource Name support."""

import re
from contextlib import suppress
from logging import getLogger
from types import MappingProxyType

from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.identifiers import (
    ANILIST_NID,
    ASIN_NID,
    COMICVINE_NID,
    COMIXOLOGY_NID,
    DEFAULT_NID,
    DEFAULT_NSS_TYPE,
    GCD_NID,
    GTIN_NID,
    IDENTIFIER_PARTS_MAP,
    ISBN_NID,
    KITSU_NID,
    LCG_NID,
    MANGADEX_NID,
    MANGAUPDATES_NID,
    MARVEL_NID,
    METRON_NID,
    MYANIMELIST_NID,
    NID_ORIGIN_MAP,
    PARSE_COMICVINE_RE,
    UPC_NID,
)

LOG = getLogger(__name__)

_CVDB_ALTERNATE_NID = "cvdb"
_CMXDB_ALTERNATE_NID = "cmxdb"

_NIDS = (
    ANILIST_NID,
    ASIN_NID,
    COMICVINE_NID,
    _CVDB_ALTERNATE_NID,
    COMIXOLOGY_NID,
    _CMXDB_ALTERNATE_NID,
    GCD_NID,
    GTIN_NID,
    ISBN_NID,
    KITSU_NID,
    LCG_NID,
    MANGADEX_NID,
    MANGAUPDATES_NID,
    MARVEL_NID,
    METRON_NID,
    MYANIMELIST_NID,
    UPC_NID,
)
IDENTIFIER_EXP = r"(?P<nid>" + r"|".join(_NIDS) + r")?:?(?P<nss>[\w-]+)"
_IDENTIFIER_URN_NID_ALIASES = MappingProxyType(
    {
        ANILIST_NID: frozenset({"anilist.co"}),
        ASIN_NID: frozenset({"amazon.com", "www.amazon.com"}),
        COMICVINE_NID: frozenset({_CVDB_ALTERNATE_NID, "comicvine.gamespot.org"}),
        COMIXOLOGY_NID: frozenset({"comixology.com", _CMXDB_ALTERNATE_NID}),
        GCD_NID: frozenset({"comics.org"}),
        GTIN_NID: frozenset({}),
        ISBN_NID: frozenset({}),
        KITSU_NID: frozenset({"kistu.app"}),
        LCG_NID: frozenset({"leagueofcomicgeeks.com"}),
        MANGADEX_NID: frozenset({"mangadex.org"}),
        MANGAUPDATES_NID: frozenset({"mangaupdates.com"}),
        MARVEL_NID: frozenset({"marvel.com"}),
        METRON_NID: frozenset({"metron.cloud"}),
        MYANIMELIST_NID: frozenset({"myanimelist.net"}),
        UPC_NID: frozenset({}),
    }
)


def _create_identifier_urn_ids_maps():
    identifier_urn_ids_reverse = {}
    for nid, aliases in _IDENTIFIER_URN_NID_ALIASES.items():
        all_aliases = aliases | {nid, NID_ORIGIN_MAP[nid].lower()}
        for alias in all_aliases:
            identifier_urn_ids_reverse[alias] = nid
    return identifier_urn_ids_reverse


IDENTIFIER_URN_NIDS_REVERSE_MAP = _create_identifier_urn_ids_maps()


# I haven't identified which program adds these "extra" notes encodings. Could be mylar.
_PARSE_EXTRA_RE = re.compile(IDENTIFIER_EXP, flags=re.IGNORECASE)


def parse_urn_identifier(tag: str, warn: bool) -> tuple[str, str, str]:
    """Parse an identifier from a tag."""
    nid = nss_type = nss = ""
    try:
        urn = URN8141.from_string(tag)
        nid = str(urn.namespace_id)
        if nid:
            nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), "")
        parts = urn.specific_string.parts
        try:
            nss_type = str(parts[-2])
        except IndexError:
            nss_type = DEFAULT_NSS_TYPE
        nss = str(parts[-1])
    except Exception as exc:
        if warn:
            LOG.debug(f"Unable to decode urn: {tag} {exc}")
    return nid, nss_type, nss


def _parse_identifier_str_comicvine(full_identifier) -> tuple[str, str, str]:
    nid = nss_type = nss = ""
    match = PARSE_COMICVINE_RE.search(full_identifier)
    if not match:
        return nid, nss_type, nss
    nid = COMICVINE_NID
    nss_type_code = match.group("nsstype") or ""
    nss_type = IDENTIFIER_PARTS_MAP[COMICVINE_NID].get_type_by_code(nss_type_code)
    nss = match.group("nss")
    return nid, nss_type, nss


def _parse_identifier_str_extra(full_identifier) -> tuple[str, str, str]:
    nid = nss_type = nss = ""
    match = _PARSE_EXTRA_RE.search(full_identifier)
    if not match:
        return nid, nss_type, nss
    with suppress(IndexError):
        nid = match.group("nid") or ""
        nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
        nss_type = DEFAULT_NSS_TYPE
        nss = match.group("nss")
    return nid, nss_type, nss


def _parse_identifier_str(full_identifier: str) -> tuple[str, str, str]:
    """Parse an identifier string with optional prefix."""
    nid, nss_type, nss = _parse_identifier_str_comicvine(full_identifier)
    if not nss:
        nid, nss_type, nss = _parse_identifier_str_extra(full_identifier)
    if not nss:
        nss = full_identifier
    return nid, nss_type, nss


def parse_string_identifier(item: str, default_nid="") -> tuple[str, str, str]:
    """Parse identifiers from strings or xml dicts."""
    nid, nss_type, nss = parse_urn_identifier(item, warn=True)
    if not nss:
        nid, nss_type, nss = _parse_identifier_str(item)
    if default_nid and not nid:
        nid = default_nid
    if not nss_type:
        nss_type = DEFAULT_NSS_TYPE

    return nid, nss_type, nss


def to_urn_string(nid_str: str, nss_type: str, nss_str: str) -> str:
    """Compose an urn string."""
    if "." in nid_str:
        return ""
    nid = NSIdentifier(nid_str)
    if nss_type:
        nss_str = nss_type + ":" + nss_str
    nss = NSSString(nss_str)
    urn = URN8141(nid=nid, nss=nss)
    return str(urn)
