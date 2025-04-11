"""Universal Resource Name support."""

from logging import getLogger

from urnparse import URN8141, NSIdentifier, NSSString

from comicbox.identifiers.const import (
    ALIAS_NID_MAP,
    DEFAULT_NSS_TYPE,
)
from comicbox.identifiers.other import parse_identifier_other_str

LOG = getLogger(__name__)


def _parse_urn_identifier(tag: str) -> tuple[str, str, str]:
    urn = URN8141.from_string(tag)
    nid = str(urn.namespace_id)
    if nid:
        nid = ALIAS_NID_MAP.get(nid.lower(), "")
    parts = urn.specific_string.parts
    try:
        nss_type = str(parts[-2])
    except IndexError:
        nss_type = DEFAULT_NSS_TYPE
    nss = str(parts[-1])
    return nid, nss_type, nss


def parse_urn_identifier_and_warn(tag: str) -> tuple[str, str, str]:
    """Parse an identifier from a tag and log a debug warning."""
    try:
        nid, nss_type, nss = _parse_urn_identifier(tag)
    except Exception as exc:
        LOG.debug(f"Unable to decode urn: {tag} {exc}")
        nid = nss_type = nss = ""
    return nid, nss_type, nss


def parse_urn_identifier(tag: str) -> tuple[str, str, str]:
    """Parse an identifier from a tag."""
    nid = nss_type = nss = ""
    try:
        nid, nss_type, nss = _parse_urn_identifier(tag)
    except Exception:
        nid = nss_type = nss = ""
    return nid, nss_type, nss


def parse_string_identifier(item: str, default_nid="") -> tuple[str, str, str]:
    """Parse identifiers from strings or xml dicts."""
    nid, nss_type, nss = parse_urn_identifier_and_warn(item)
    if not nss:
        nid, nss_type, nss = parse_identifier_other_str(item)
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
