"""MetronInfo.xml Identifiers & URLs Transform."""

from collections.abc import Iterator, Mapping
from contextlib import suppress
from types import MappingProxyType
from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import ID_SOURCE_NAME_MAP
from comicbox.enums.metroninfo import MetronSourceEnum
from comicbox.formats.base.fields.xml_fields import get_cdata
from comicbox.formats.base.transforms.identifiers import (
    PRIMARY_ID_SOURCE_KEYPATH,
    urls_to_cb,
)
from comicbox.formats.base.transforms.spec import GLOBAL_SCOPE_PREFIX, MetaSpec
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    PRIMARY_ID_SOURCE_KEY,
    URLS_KEY,
)
from comicbox.formats.metron_info.transform.const import DEFAULT_ID_SOURCE_STR
from comicbox.identifiers import (
    BARCODE_ID_SOURCES,
    DEFAULT_ID_TYPE,
    ID_KEY_KEY,
    ID_TYPE_KEY,
    ranked_id_sources,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
    get_id_source_from_url,
    get_url_from_identifier,
)

PRIMARY_ATTRIBUTE = "@primary"
SOURCE_ATTRIBUTE = "@source"
# MetronInfo's <GTIN> holds only ISBN and UPC subtags, never the generic
# GTIN, and its subtag names are the IdSources member names.
GTIN_SUBTAG_ID_SOURCE_MAP = MappingProxyType(
    {
        id_source.name: id_source.value
        for id_source in BARCODE_ID_SOURCES
        if id_source is not IdSources.GTIN
    }
)
ID_KEYPATH = "IDS.ID"
URL_KEYPATH = "URLs.URL"
SCOPE_PRIMARY_SOURCE = f"{GLOBAL_SCOPE_PREFIX}.{PRIMARY_ID_SOURCE_KEYPATH}"
GTIN_TAG = "GTIN"


def is_item_primary(
    native_identifier: Any,
) -> bool:
    """Parse primary attribute."""
    return (
        bool(native_identifier and native_identifier.get(PRIMARY_ATTRIBUTE))
        if isinstance(native_identifier, Mapping)
        else False
    )


def _primary_id_source_from_ids(metron_ids: list[Any]) -> str | None:
    for metron_id in metron_ids:
        if (
            is_item_primary(metron_id)
            and (metron_id_source := metron_id.get(SOURCE_ATTRIBUTE))
            and (id_source := getattr(IdSources, metron_id_source.name, None))
        ):
            return id_source.value
    return None


def _primary_id_source_from_urls(metron_urls: list[Any]) -> str | None:
    for metron_url in metron_urls:
        if not is_item_primary(metron_url):
            continue
        if (url := get_cdata(metron_url)) and (
            id_source_str := get_id_source_from_url(str(url))
        ):
            return id_source_str
    return None


def _primary_id_source_to_cb(
    values: dict[str, Any],
) -> dict[str, str] | None:
    if (
        (metron_identifiers := values.get(ID_KEYPATH))
        and (id_source_str := _primary_id_source_from_ids(metron_identifiers))
    ) or (
        (metron_urls := values.get(URL_KEYPATH))
        and (id_source_str := _primary_id_source_from_urls(metron_urls))
    ):
        return {PRIMARY_ID_SOURCE_KEY: id_source_str}
    return None


METRON_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB = MetaSpec(
    key_map={PRIMARY_ID_SOURCE_KEY: (ID_KEYPATH, URL_KEYPATH)},
    spec=_primary_id_source_to_cb,
    assign_global=True,
)


def _identifier_to_cb(native_identifier: Any) -> tuple[str, dict]:
    """Parse metron identifier type into components."""
    if not isinstance(native_identifier, Mapping):
        return "", {}
    source_str = native_identifier.get(SOURCE_ATTRIBUTE)
    source_name = getattr(source_str, "name", source_str)
    id_source = (
        getattr(IdSources, source_name, None) if isinstance(source_name, str) else None
    )
    id_source_str = id_source.value if id_source else ""
    id_key = get_cdata(native_identifier)
    if not isinstance(id_key, str):
        id_key = ""
    identifier = create_identifier(
        id_source_str,
        id_key,
        default_id_source_str=DEFAULT_ID_SOURCE_STR,
    )
    return id_source_str, identifier


def _identifiers_to_cb_ids(values: dict[str, Any]) -> dict:
    id_identifiers = {}
    if metron_ids := values.get(ID_KEYPATH):
        for metron_id in metron_ids:
            id_source, identifier = _identifier_to_cb(metron_id)
            if id_source and identifier:
                id_identifiers[id_source] = identifier
    return id_identifiers


def _identifiers_to_cb_gtin(values: dict[str, Any]) -> dict:
    gtin_identifiers = {}
    if metron_gtin := values.get(GTIN_TAG, {}):
        for tag, id_source_str in GTIN_SUBTAG_ID_SOURCE_MAP.items():
            if id_key := metron_gtin.get(tag):
                identifier = create_identifier(
                    id_source_str, id_key, default_id_source_str=DEFAULT_ID_SOURCE_STR
                )
                if identifier:
                    gtin_identifiers[id_source_str] = identifier
    return gtin_identifiers


def identifiers_to_cb(values: dict) -> dict:
    """Aggregate IDS and GTIN into comicbox identifiers."""
    # URLs no longer contribute here. They are kept verbatim in `urls`, and
    # the computed layer derives an identifier from a recognized url when no
    # explicit id supplied one. A url path is a slug for several databases,
    # so it must never overwrite an authoritative <ID>.
    return {**_identifiers_to_cb_gtin(values), **_identifiers_to_cb_ids(values)}


METRON_IDENTIFIERS_TRANSFORM_TO_CB = MetaSpec(
    {IDENTIFIERS_KEY: (ID_KEYPATH, GTIN_TAG)},
    spec=identifiers_to_cb,
)

METRON_URLS_TRANSFORM_TO_CB = MetaSpec(
    {URLS_KEY: URL_KEYPATH},
    spec=urls_to_cb,
)


def _metron_id_source(id_source_str: str) -> MetronSourceEnum | None:
    with suppress(ValueError):
        id_source = IdSources(id_source_str)
        id_source_name = ID_SOURCE_NAME_MAP.get(id_source, "")
        return MetronSourceEnum(id_source_name)
    return None


def _ids_from_cb(comicbox_identifiers: Mapping) -> list[tuple[str, dict]]:
    """Return (id source, metron <ID>) for each issue id <IDS> can hold."""
    metron_identifiers = []
    for id_source_str, comicbox_identifier in comicbox_identifiers.items():
        if id_source_str in GTIN_SUBTAG_ID_SOURCE_MAP.values():
            continue
        id_type = comicbox_identifier.get(ID_TYPE_KEY) or DEFAULT_ID_TYPE
        if id_type != DEFAULT_ID_TYPE:
            # IDS holds this issue's ids. A series or character id written
            # here reads back as an issue id, and the url built from it
            # points at an issue that doesn't exist. It still travels in
            # URLs and in the Notes urns.
            continue
        metron_id_source = _metron_id_source(id_source_str)
        if not metron_id_source:
            continue
        if id_key := comicbox_identifier.get(ID_KEY_KEY):
            metron_identifiers.append(
                (id_source_str, {SOURCE_ATTRIBUTE: metron_id_source, "#text": id_key})
            )
    return metron_identifiers


def _url_sources_from_cb(
    comicbox_urls: Any, comicbox_identifiers: Mapping
) -> tuple[list[str], list[str]]:
    """
    Return the urls to write and the id source of each.

    A stored url always wins: it came from the file, while a derived one is
    comicbox's best guess from the id.
    """
    urls: dict[str, None] = {}
    for url in comicbox_urls or ():
        urls[str(url)] = None
    id_source_by_url: dict[str, str] = {}
    for id_source_str, comicbox_identifier in comicbox_identifiers.items():
        if url := get_url_from_identifier(id_source_str, comicbox_identifier):
            urls.setdefault(url, None)
            id_source_by_url.setdefault(url, id_source_str)
    url_list = list(urls)
    url_sources = [
        id_source_by_url.get(url) or get_id_source_from_url(url) for url in url_list
    ]
    return url_list, url_sources


def _nested_id_sources(node: Any) -> Iterator[str]:
    """Yield the id sources of every identifiers dict below the top level."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == IDENTIFIERS_KEY and isinstance(value, Mapping):
                yield from value
            else:
                yield from _nested_id_sources(value)
    elif isinstance(node, list | tuple):
        for item in node:
            yield from _nested_id_sources(item)


def metron_primary_id_source_from_cb(comicbox: Mapping) -> str:
    """
    Choose the one id source the written file names primary.

    A reader files every bare tag `id` under the flagged <ID>, else the
    flagged <URL>, else Metron. So the source chosen here has to be one a
    flag can name, or Metron, and every writer has to use it: the <IDS> and
    <URLs> flags and each tag `id`. A stated primary_id_source wins. Without
    one, the best ranked source among all the ids present.
    """
    comicbox_identifiers = comicbox.get(IDENTIFIERS_KEY) or {}
    ids_sources = [
        id_source_str for id_source_str, _ in _ids_from_cb(comicbox_identifiers)
    ]
    _, url_sources = _url_sources_from_cb(comicbox.get(URLS_KEY), comicbox_identifiers)
    flaggable = {*ids_sources, *filter(None, url_sources)}
    expressible = {DEFAULT_ID_SOURCE_STR, *flaggable}
    explicit = comicbox.get(PRIMARY_ID_SOURCE_KEY)
    if explicit in expressible:
        return explicit
    tags = {key: value for key, value in comicbox.items() if key != IDENTIFIERS_KEY}
    present = {*flaggable, *_nested_id_sources(tags)}
    return next(ranked_id_sources(present & expressible), DEFAULT_ID_SOURCE_STR)


def _flag_primary(
    metron_objs: list[dict[str, Any]],
    id_sources: list[str],
    primary_id_source_str: str,
) -> None:
    """
    Flag the entry of the primary source, or none.

    No flag when the primary source has no entry: the reader then falls
    back to Metron, which metron_primary_id_source_from_cb only allows when
    Metron is the primary.
    """
    if primary_id_source_str in id_sources:
        metron_objs[id_sources.index(primary_id_source_str)][PRIMARY_ATTRIBUTE] = True


def identifiers_from_cb(values: dict[str, Any]) -> list:
    """Unparse comicbox identifiers to metron ID tags."""
    comicbox_identifiers = values.get(IDENTIFIERS_KEY)
    if not comicbox_identifiers:
        return []
    primary_id_source_str = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE_STR)
    pairs = _ids_from_cb(comicbox_identifiers)
    metron_identifiers = [metron_identifier for _, metron_identifier in pairs]
    id_sources = [id_source_str for id_source_str, _ in pairs]
    _flag_primary(metron_identifiers, id_sources, primary_id_source_str)
    return metron_identifiers


METRON_IDENTIFIERS_TRANSFORM_FROM_CB = MetaSpec(
    {ID_KEYPATH: (IDENTIFIERS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=identifiers_from_cb,
)


def _gtin_from_cb(identifiers: dict[str, dict[str, str]]) -> dict | None:
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


def _urls_from_cb(values: dict[str, Any]) -> list:
    """Write the verbatim urls, plus a derived one for any id lacking one."""
    url_list, url_sources = _url_sources_from_cb(
        values.get(URLS_KEY), values.get(IDENTIFIERS_KEY) or {}
    )
    if not url_list:
        return []
    primary_id_source_str = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE_STR)
    metron_urls: list[dict[str, Any]] = [{"#text": url} for url in url_list]
    _flag_primary(metron_urls, url_sources, primary_id_source_str)
    return metron_urls


METRON_URLS_TRANSFORM_FROM_CB = MetaSpec(
    key_map={URL_KEYPATH: (URLS_KEY, IDENTIFIERS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_urls_from_cb,
)
