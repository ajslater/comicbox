"""MetronInfo.xml Identifiers & URLs Transform."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from glom import glom

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    IDENTIFIER_PARTS_MAP,
    ISBN_NID,
    METRON_NID,
    NID_ORIGIN_MAP,
    UPC_NID,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    NID_KEY,
)
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.transforms.identifiers import (
    create_identifier_primary_source,
    get_primary_source_nid,
    url_from_cb,
    urls_to_cb,
)
from comicbox.transforms.transform_map import DUMMY_PREFIX, KeyTransforms

DEFAULT_NID = "metron"
PRIMARY_ATTRIBUTE = "@primary"
SOURCE_ATTRIBUTE = "@source"
GTIN_SUBTAG_NID_MAP = MappingProxyType({"ISBN": ISBN_NID, "UPC": UPC_NID})
ID_KEY_PATH = "IDS.ID"
URL_KEY_PATH = "URLs.URL"


def _identifier_to_cb(native_identifier):
    """Parse metron identifier type into components."""
    source = native_identifier.get(SOURCE_ATTRIBUTE, "")
    if isinstance(source, Enum):
        source = source.value
    nid = NID_ORIGIN_MAP.inverse.get(source, "")
    nss_type = "issue"
    nss = get_cdata(native_identifier) or "" if nid else ""
    identifier = create_identifier(nid, nss, nss_type=nss_type)
    return nid, identifier


def identifiers_to_cb(_source_data: dict, metron_ids: list) -> dict:
    """Hoist Identifiers before parsing."""
    comicbox_identifiers = {}
    for metron_id in metron_ids:
        nid, identifier = _identifier_to_cb(metron_id)
        comicbox_identifiers[nid] = identifier
    return comicbox_identifiers


def identifiers_from_cb(source_data: dict, comicbox_identifiers: dict) -> list:
    """Unparse one identifier to an xml metron GTIN or ID tag."""
    metron_identifiers = []
    primary_set = False
    for nid, comicbox_identifier in comicbox_identifiers.items():
        if (
            (nid not in GTIN_SUBTAG_NID_MAP.values())
            and (nid_value := NID_ORIGIN_MAP.get(nid))
            and (nss := comicbox_identifier.get(NSS_KEY))
        ):
            metron_identifier = {SOURCE_ATTRIBUTE: nid_value, "#text": nss}
            primary_nid = get_primary_source_nid(source_data, METRON_NID)
            if nid == primary_nid:
                metron_identifier[PRIMARY_ATTRIBUTE] = True
                primary_set = True
            metron_identifiers.append(metron_identifier)
    if metron_identifiers and not primary_set:
        # This can ignore identifiers aggregated from series alternative names.
        # But I think that's usually fine.
        metron_identifiers[0][PRIMARY_ATTRIBUTE] = True

    return metron_identifiers


METRON_IDENTIFIERS_TRANSFORM = KeyTransforms(
    {ID_KEY_PATH: IDENTIFIERS_KEY}, to_cb=identifiers_to_cb, from_cb=identifiers_from_cb
)


def _gtin_to_cb(_source_data, metron_gtin):
    """Parse complex metron gtin structure into identifiers."""
    comicbox_identifiers = {}
    for tag, nid in GTIN_SUBTAG_NID_MAP.items():
        if nss := metron_gtin.get(tag):
            identifier = create_identifier(nid, nss)
            comicbox_identifiers[nid] = identifier
    return comicbox_identifiers


def _gtin_from_cb(_source_data, identifiers):
    """Unparse GTIN from identifier as a side effect."""
    gtin = {}
    for tag, nid in GTIN_SUBTAG_NID_MAP.items():
        if nss := identifiers.get(nid, {}).get(NSS_KEY):
            gtin[tag] = nss
    return gtin


METRON_GTIN_TRANSFORM = KeyTransforms(
    key_map={"GTIN": IDENTIFIERS_KEY}, to_cb=_gtin_to_cb, from_cb=_gtin_from_cb
)


def _urls_from_cb(source_data, comicbox_identifiers):
    metron_urls = []
    primary_nid = get_primary_source_nid(source_data, METRON_NID)
    primary_set = False
    for nid, comicbox_identifier in comicbox_identifiers.items():
        if url := url_from_cb(nid, comicbox_identifier):
            metron_url: dict[str, Any] = {"#text": url}
            if primary_nid == nid:
                metron_url[PRIMARY_ATTRIBUTE] = True
                primary_set = True
            metron_urls.append(metron_url)
    if metron_urls and not primary_set:
        metron_urls[0][PRIMARY_ATTRIBUTE] = True

    return metron_urls


METRON_URLS_TRANSFORM = KeyTransforms(
    key_map={URL_KEY_PATH: IDENTIFIERS_KEY}, to_cb=urls_to_cb, from_cb=_urls_from_cb
)


def is_item_primary(native_identifier) -> bool:
    """Parse primary attribute."""
    return (
        bool(native_identifier.get(PRIMARY_ATTRIBUTE))
        if isinstance(native_identifier, Mapping)
        else False
    )


def _identifier_primary_source_to_cb_ids(source_data):
    id_key_path = f"{MetronInfoSchema.ROOT_KEY_PATH}.{ID_KEY_PATH}"
    metron_ids = glom(source_data, id_key_path, default=())
    for metron_id in metron_ids:
        if (
            is_item_primary(metron_id)
            and (source_enum := metron_id.get(SOURCE_ATTRIBUTE))
            and (nid := NID_ORIGIN_MAP.inverse.get(source_enum.value))
        ):
            id_parts = IDENTIFIER_PARTS_MAP[nid]
            return {NID_KEY: nid, URL_KEY: id_parts.url_prefix}
    return None


def _identifier_primary_source_to_cb_urls(source_data):
    url_key_path = f"{MetronInfoSchema.ROOT_KEY_PATH}.{URL_KEY_PATH}"
    metron_urls = glom(source_data, url_key_path, default=())
    for metron_url in metron_urls:
        if not is_item_primary(metron_url):
            continue
        parsed_url = urlparse(metron_url)
        if not parsed_url:
            continue
        netloc = parsed_url.netloc
        if not netloc:
            continue
        for nid, id_parts in IDENTIFIER_PARTS_MAP.items():
            if netloc.endswith(id_parts.domain):
                return create_identifier_primary_source(nid)
    return None


def _identifier_primary_source_to_cb(source_data, _):
    if ips := _identifier_primary_source_to_cb_ids(source_data):
        return ips
    if ips := _identifier_primary_source_to_cb_urls(source_data):
        return ips
    return None


METRON_PRIMARY_SOURCE_KEY_TRANSFORM = KeyTransforms(
    key_map={
        f"{DUMMY_PREFIX}_identifier_primary_source": IDENTIFIER_PRIMARY_SOURCE_KEY
    },
    to_cb=_identifier_primary_source_to_cb,
)
