"""MetronInfo.xml Identifiers & URLs Transform."""

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    ID_KEY_KEY,
    ID_SOURCE_NAME_MAP,
    URL_KEY,
    IdSources,
)
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
    create_identifier,
)
from comicbox.merge import AdditiveMerger
from comicbox.schemas.comicbox import (
    ID_SOURCE_KEY,
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
)
from comicbox.transforms.identifiers import (
    PRIMARY_ID_SOURCE_KEYPATH,
    create_identifier_primary_source,
    url_from_cb,
    urls_to_cb,
)
from comicbox.transforms.metroninfo.const import DEFAULT_ID_SOURCE
from comicbox.transforms.spec import GLOBAL_SCOPE_PREFIX, MetaSpec

PRIMARY_ATTRIBUTE = "@primary"
SOURCE_ATTRIBUTE = "@source"
GTIN_SUBTAG_ID_SOURCE_MAP = MappingProxyType(
    {"ISBN": IdSources.ISBN.value, "UPC": IdSources.UPC.value}
)
ID_KEYPATH = "IDS.ID"
URL_KEYPATH = "URLs.URL"
SCOPE_PRIMARY_SOURCE = f"{GLOBAL_SCOPE_PREFIX}.{PRIMARY_ID_SOURCE_KEYPATH}"
GTIN_TAG = "GTIN"


def is_item_primary(native_identifier) -> bool:
    """Parse primary attribute."""
    return (
        bool(native_identifier and native_identifier.get(PRIMARY_ATTRIBUTE))
        if isinstance(native_identifier, Mapping)
        else False
    )


def _identifier_primary_source_to_cb_ids(metron_ids):
    for metron_id in metron_ids:
        if (
            is_item_primary(metron_id)
            and (source_enum := metron_id.get(SOURCE_ATTRIBUTE))
            and (id_source := ID_SOURCE_NAME_MAP.inverse.get(source_enum.value))
        ):
            id_parts = IDENTIFIER_PARTS_MAP[id_source]
            return {ID_SOURCE_KEY: id_source, URL_KEY: id_parts.url_prefix}
    return None


def _parse_url(metron_url):
    parsed_url = None
    if url := get_cdata(metron_url):
        parsed_url = urlparse(str(url))
    return parsed_url


def _identifier_primary_source_to_cb_urls(metron_urls):
    for metron_url in metron_urls:
        if not is_item_primary(metron_url):
            continue
        parsed_url = _parse_url(metron_url)
        if not parsed_url:
            continue
        netloc = parsed_url.netloc
        if not netloc:
            continue
        for id_source, id_parts in IDENTIFIER_PARTS_MAP.items():
            if str(netloc).endswith(id_parts.domain):
                return create_identifier_primary_source(id_source)
    return None


def _identifier_primary_source_to_cb(values):
    if (
        (metron_identifiers := values.get(ID_KEYPATH))
        and (ips := _identifier_primary_source_to_cb_ids(metron_identifiers))
    ) or (
        (metron_urls := values.get(URL_KEYPATH))
        and (ips := _identifier_primary_source_to_cb_urls(metron_urls))
    ):
        return {IDENTIFIER_PRIMARY_SOURCE_KEY: ips}
    return None


METRON_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB = MetaSpec(
    key_map={IDENTIFIER_PRIMARY_SOURCE_KEY: (ID_KEYPATH, URL_KEYPATH)},
    spec=_identifier_primary_source_to_cb,
    assign_global=True,
)


def _identifier_to_cb(native_identifier):
    """Parse metron identifier type into components."""
    source = native_identifier.get(SOURCE_ATTRIBUTE, "")
    if isinstance(source, Enum):
        source = source.value
    id_source = ID_SOURCE_NAME_MAP.inverse.get(source, "")
    id_type = "issue"
    id_key = get_cdata(native_identifier) or "" if id_source else ""
    identifier = create_identifier(
        id_source, id_key, id_type=id_type, default_id_source=DEFAULT_ID_SOURCE
    )
    return id_source, identifier


def _identifiers_to_cb_identifiers(values):
    id_identifiers = {}
    if metron_ids := values.get(ID_KEYPATH):
        for metron_id in metron_ids:
            id_source, identifier = _identifier_to_cb(metron_id)
            id_identifiers[id_source] = identifier
    return id_identifiers


def _identifers_to_cb_gtin(values):
    gtin_identifiers = {}
    if metron_gtin := values.get(GTIN_TAG, {}):
        for tag, id_source in GTIN_SUBTAG_ID_SOURCE_MAP.items():
            if id_key := metron_gtin.get(tag):
                identifier = create_identifier(
                    id_source, id_key, default_id_source=DEFAULT_ID_SOURCE
                )
                gtin_identifiers[id_source] = identifier
    return gtin_identifiers


def _identifiers_to_cb_urls(values):
    metron_urls = values.get(URL_KEYPATH, {})
    return urls_to_cb(metron_urls)


def identifiers_to_cb(values: dict) -> dict:
    """Aggregate IDS, GTIN and URLs into comicbox identifiers."""
    id_identifiers = _identifiers_to_cb_identifiers(values)
    gtin_identifiers = _identifers_to_cb_gtin(values)
    url_identifiers = _identifiers_to_cb_urls(values)
    comicbox_identifiers = {}
    AdditiveMerger.merge(
        comicbox_identifiers, id_identifiers, gtin_identifiers, url_identifiers
    )
    return comicbox_identifiers


METRON_IDENTIFIERS_TRANSFORM_TO_CB = MetaSpec(
    {IDENTIFIERS_KEY: (ID_KEYPATH, GTIN_TAG, URL_KEYPATH, SCOPE_PRIMARY_SOURCE)},
    spec=identifiers_to_cb,
)


def identifiers_from_cb(values) -> list:
    """Unparse one identifier to an xml metron GTIN or ID tag."""
    comicbox_identifiers = values.get(IDENTIFIERS_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    metron_identifiers = []
    primary_set = False
    for id_source, comicbox_identifier in comicbox_identifiers.items():
        if (
            (id_source not in GTIN_SUBTAG_ID_SOURCE_MAP.values())
            and (id_source_value := ID_SOURCE_NAME_MAP.get(id_source))
            and (id_key := comicbox_identifier.get(ID_KEY_KEY))
        ):
            metron_identifier = {SOURCE_ATTRIBUTE: id_source_value, "#text": id_key}
            if id_source == primary_id_source:
                metron_identifier[PRIMARY_ATTRIBUTE] = True
                primary_set = True
            metron_identifiers.append(metron_identifier)
    if metron_identifiers and not primary_set:
        # This can ignore identifiers aggregated from series alternative names.
        # But I think that's usually fine.
        metron_identifiers[0][PRIMARY_ATTRIBUTE] = True

    return metron_identifiers


METRON_IDENTIFIERS_TRANSFORM_FROM_CB = MetaSpec(
    {ID_KEYPATH: (IDENTIFIERS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=identifiers_from_cb,
)


def _gtin_from_cb(identifiers):
    """Unparse GTIN from identifier as a side effect."""
    gtin = {}
    for tag, id_source in GTIN_SUBTAG_ID_SOURCE_MAP.items():
        if id_key := identifiers.get(id_source, {}).get(ID_KEY_KEY):
            gtin[tag] = id_key
    if not gtin:
        gtin = None
    return gtin


METRON_GTIN_TRANSFORM_FROM_CB = MetaSpec(
    key_map={"GTIN": IDENTIFIERS_KEY}, spec=_gtin_from_cb
)


def _urls_from_cb(values):
    comicbox_identifiers = values.get(IDENTIFIERS_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    metron_urls = []
    primary_set = False
    for id_source, comicbox_identifier in comicbox_identifiers.items():
        if url := url_from_cb(id_source, comicbox_identifier):
            metron_url: dict[str, Any] = {"#text": url}
            if primary_id_source == id_source:
                metron_url[PRIMARY_ATTRIBUTE] = True
                primary_set = True
            metron_urls.append(metron_url)
    if metron_urls and not primary_set:
        metron_urls[0][PRIMARY_ATTRIBUTE] = True

    return metron_urls


METRON_URLS_TRANSFORM_FROM_CB = MetaSpec(
    key_map={URL_KEYPATH: (IDENTIFIERS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_urls_from_cb,
)
