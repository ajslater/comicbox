"""Non urn identifier substring parsers."""

import re
from contextlib import suppress

from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.identifiers import (
    DEFAULT_ID_TYPE,
    IDENTIFIER_RE_EXP,
    PARSE_COMICVINE_RE,
    match_id_source_str,
)
from comicbox.identifiers.identifiers import IDENTIFIER_PARTS_MAP

# I haven't identified which program adds these other notes encodings. Could be mylar.
_PARSE_OTHER_RE = re.compile(IDENTIFIER_RE_EXP, flags=re.IGNORECASE)


def _parse_identifier_str_comicvine(
    full_identifier: str,
) -> tuple[IdSources | None, str, str]:
    id_source = None
    id_type = id_key = ""
    match = PARSE_COMICVINE_RE.fullmatch(full_identifier)
    if not match:
        return id_source, id_type, id_key
    id_source = IdSources.COMICVINE
    id_type_code = match.group("id_type") or ""
    id_type = IDENTIFIER_PARTS_MAP[id_source].get_type_by_code(id_type_code)
    id_key = match.group("id_key")
    return id_source, id_type, id_key


def _parse_identifier_other_str(
    full_identifier: str,
) -> tuple[IdSources | None, str, str]:
    id_source = None
    id_type = id_key = ""
    match = _PARSE_OTHER_RE.fullmatch(full_identifier)
    if not match:
        return id_source, id_type, id_key
    with suppress(IndexError):
        id_source = get_id_source_by_alias(match_id_source_str(match))
        id_type = (match.group("id_type") or DEFAULT_ID_TYPE).lower()
        id_key = match.group("id_key")
    return id_source, id_type, id_key


def parse_identifier_other_str(
    full_identifier: str,
) -> tuple[IdSources | None, str, str]:
    """
    Parse an identifier string with optional prefix.

    The string has to be an identifier and nothing else. Matching a
    substring turned every tag and genre that merely contained something
    identifier shaped into an id: "marvel-comics" was a marvel id, and a
    year range like "2019-2021" was a comicvine one.
    """
    full_identifier = full_identifier.strip()
    id_source, id_type, id_key = _parse_identifier_str_comicvine(full_identifier)
    if not id_key:
        id_source, id_type, id_key = _parse_identifier_other_str(full_identifier)
    if not id_key:
        id_key = full_identifier
    return id_source, id_type, id_key
