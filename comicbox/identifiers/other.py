"""Non urn identifier substring parsers."""

import re
from contextlib import suppress

from comicbox.identifiers.const import (
    ALIAS_NID_MAP,
    DEFAULT_NID,
    DEFAULT_NSS_TYPE,
    IDENTIFIER_RE_EXP,
    PARSE_COMICVINE_RE,
    NIDs,
)
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
)

# I haven't identified which program adds these other notes encodings. Could be mylar.
_PARSE_OTHER_RE = re.compile(IDENTIFIER_RE_EXP, flags=re.IGNORECASE)


def _parse_identifier_str_comicvine(full_identifier) -> tuple[str, str, str]:
    nid = nss_type = nss = ""
    match = PARSE_COMICVINE_RE.search(full_identifier)
    if not match:
        return nid, nss_type, nss
    nid = NIDs.COMICVINE.value
    nss_type_code = match.group("nsstype") or ""
    nss_type = IDENTIFIER_PARTS_MAP[nid].get_type_by_code(nss_type_code)
    nss = match.group("nss")
    return nid, nss_type, nss


def _parse_identifier_other_str(full_identifier) -> tuple[str, str, str]:
    nid = nss_type = nss = ""
    match = _PARSE_OTHER_RE.search(full_identifier)
    if not match:
        return nid, nss_type, nss
    with suppress(IndexError):
        nid = match.group("nid") or ""
        nid = ALIAS_NID_MAP.get(nid.lower(), DEFAULT_NID)
        nss_type = DEFAULT_NSS_TYPE
        nss = match.group("nss")
    return nid, nss_type, nss


def parse_identifier_other_str(full_identifier: str) -> tuple[str, str, str]:
    """Parse an identifier string with optional prefix."""
    nid, nss_type, nss = _parse_identifier_str_comicvine(full_identifier)
    if not nss:
        nid, nss_type, nss = _parse_identifier_other_str(full_identifier)
    if not nss:
        nss = full_identifier
    return nid, nss_type, nss
