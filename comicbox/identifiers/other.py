"""Non urn identifier substring parsers."""

import re
from contextlib import suppress

from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_SOURCE,
    DEFAULT_ID_TYPE,
    IDENTIFIER_RE_EXP,
    PARSE_COMICVINE_RE,
    IdSources,
)
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
)

# I haven't identified which program adds these other notes encodings. Could be mylar.
_PARSE_OTHER_RE = re.compile(IDENTIFIER_RE_EXP, flags=re.IGNORECASE)


def _parse_identifier_str_comicvine(full_identifier) -> tuple[str, str, str]:
    id_source = id_type = id_key = ""
    match = PARSE_COMICVINE_RE.search(full_identifier)
    if not match:
        return id_source, id_type, id_key
    id_source = IdSources.COMICVINE.value
    id_type_code = match.group("id_keytype") or ""
    id_type = IDENTIFIER_PARTS_MAP[id_source].get_type_by_code(id_type_code)
    id_key = match.group("id_key")
    return id_source, id_type, id_key


def _parse_identifier_other_str(full_identifier) -> tuple[str, str, str]:
    id_source = id_type = id_key = ""
    match = _PARSE_OTHER_RE.search(full_identifier)
    if not match:
        return id_source, id_type, id_key
    with suppress(IndexError):
        id_source = match.group("id_source") or ""
        id_source = ALIAS_ID_SOURCE_MAP.get(id_source.lower(), DEFAULT_ID_SOURCE)
        id_type = DEFAULT_ID_TYPE
        id_key = match.group("id_key")
    return id_source, id_type, id_key


def parse_identifier_other_str(full_identifier: str) -> tuple[str, str, str]:
    """Parse an identifier string with optional prefix."""
    id_source, id_type, id_key = _parse_identifier_str_comicvine(full_identifier)
    if not id_key:
        id_source, id_type, id_key = _parse_identifier_other_str(full_identifier)
    if not id_key:
        id_key = full_identifier
    return id_source, id_type, id_key
