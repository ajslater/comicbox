"""Universal Resource Name support."""

from loguru import logger
from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_TYPE,
)
from comicbox.identifiers.other import parse_identifier_other_str


def _parse_urn_identifier(tag: str) -> tuple[str, str, str]:
    urn = URN8141.from_string(tag)
    id_source = str(urn.namespace_id)
    if id_source:
        id_source = ALIAS_ID_SOURCE_MAP.get(id_source.lower(), "")
    parts = urn.specific_string.parts
    try:
        id_type = str(parts[-2])
    except IndexError:
        id_type = DEFAULT_ID_TYPE
    id_key = str(parts[-1])
    return id_source, id_type, id_key


def parse_urn_identifier_and_warn(tag: str) -> tuple[str, str, str]:
    """Parse an identifier from a tag and log a debug warning."""
    try:
        id_source, id_type, id_key = _parse_urn_identifier(tag)
    except Exception as exc:
        logger.debug(f"Unable to decode urn: {tag} {exc}")
        id_source = id_type = id_key = ""
    return id_source, id_type, id_key


def parse_urn_identifier(tag: str) -> tuple[str, str, str]:
    """Parse an identifier from a tag."""
    id_source = id_type = id_key = ""
    try:
        id_source, id_type, id_key = _parse_urn_identifier(tag)
    except Exception:
        id_source = id_type = id_key = ""
    return id_source, id_type, id_key


def parse_string_identifier(item: str, default_id_source="") -> tuple[str, str, str]:
    """Parse identifiers from strings or xml dicts."""
    id_source, id_type, id_key = parse_urn_identifier_and_warn(item)
    if not id_key:
        id_source, id_type, id_key = parse_identifier_other_str(item)
    if default_id_source and not id_source:
        id_source = default_id_source
    if not id_type:
        id_type = DEFAULT_ID_TYPE

    return id_source, id_type, id_key


def to_urn_string(id_source_str: str, id_type: str, id_key_str: str) -> str:
    """Compose an urn string."""
    if "." in id_source_str:
        return ""
    id_source = NSIdentifier(id_source_str)
    if id_type:
        id_key_str = id_type + ":" + id_key_str
    id_key = NSSString(id_key_str)
    urn = URN8141(nid=id_source, nss=id_key)
    return str(urn)
