"""
Universal Resource Name support.

Comicbox writes and reads one shape of RFC 8141 urn:

    urn:<id_source>[:<id_type>]:<id_key>

The type segment is written only when the identifier's type differs from the
one implied by where it sits, which for a urn is always ``issue``. Both forms
parse, as do the typed urns comicbox wrote before v3 and comicvine long codes.

These functions never raise. A source or key that cannot form a legal urn
yields the empty string rather than an exception, because the notes stamp
composes urns from arbitrary user-supplied identifier sources.
"""

import re
from urllib.parse import unquote

from loguru import logger

from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_TYPE_NAMES
from comicbox.identifiers.other import parse_identifier_other_str

_ID_TYPES = frozenset(ID_TYPE_NAMES)
# RFC 8141 §2: 2-32 chars, alphanumeric at both ends, hyphens inside.
_NID_EXP = r"[A-Za-z0-9][A-Za-z0-9-]{0,30}[A-Za-z0-9]"
_NID_RE = re.compile(_NID_EXP)
# The scheme is case insensitive per RFC 8141 §2.
_URN_RE = re.compile(rf"urn:(?P<nid>{_NID_EXP}):(?P<nss>\S+)", re.IGNORECASE)
_URN_SCHEME = "urn:"
_WHITESPACE_RE = re.compile(r"\s")


def _is_urn(tag: str) -> bool:
    """Say whether a string even claims to be a urn."""
    return tag[: len(_URN_SCHEME)].lower() == _URN_SCHEME


def parse_urn_identifier(tag: str) -> tuple[IdSources | None, str, str]:
    """Parse an identifier from a urn."""
    match = _URN_RE.fullmatch(tag.strip())
    if not match:
        if _is_urn(tag):
            logger.debug(f"Unable to decode urn: {tag}")
        return None, "", ""
    id_source = get_id_source_by_alias(match.group("nid"), None)
    nss = match.group("nss")
    if "%" in nss:
        # Comicbox used to decode with a library that did this. Keys other
        # taggers percent encoded still arrive decoded.
        nss = unquote(nss)
    id_type, sep, id_key = nss.partition(":")
    id_type = id_type.lower()
    if sep and id_type in _ID_TYPES:
        return id_source, id_type, id_key
    # An unrecognized first segment is part of the key, not a type. Dropping
    # it would silently discard whatever a hand tagger meant by it.
    return id_source, DEFAULT_ID_TYPE, nss


def parse_string_identifier(
    item: str, default_id_source: IdSources | None = None
) -> tuple[IdSources | None, str, str]:
    """Parse identifiers from strings or xml dicts."""
    id_source = None
    id_type = id_key = ""
    if _is_urn(item):
        id_source, id_type, id_key = parse_urn_identifier(item)
    if not id_key:
        id_source, id_type, id_key = parse_identifier_other_str(item)
    if not id_source:
        id_source = default_id_source
    if not id_type:
        id_type = DEFAULT_ID_TYPE
    return id_source, id_type, id_key


def to_urn_string(id_source_str: str, id_type: str, id_key_str: str) -> str:
    """
    Compose an urn string.

    Returns the empty string for parts that cannot make a legal urn, so a
    hand written identifier source or key never aborts a read.
    """
    if (
        not _NID_RE.fullmatch(id_source_str)
        or not id_key_str
        or _WHITESPACE_RE.search(id_key_str)
    ):
        return ""
    id_type = id_type.lower()
    if id_type in ("", DEFAULT_ID_TYPE):
        return f"urn:{id_source_str}:{id_key_str}"
    if id_type not in _ID_TYPES:
        # Naming a type comicbox doesn't know would read back as an issue id.
        return ""
    return f"urn:{id_source_str}:{id_type}:{id_key_str}"
