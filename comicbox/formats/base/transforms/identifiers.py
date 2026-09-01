"""Identifier Fields."""

from typing import Any

from loguru import logger

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.fields.xml_fields import get_cdata
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    PRIMARY_ID_SOURCE_KEY,
    URLS_KEY,
)
from comicbox.identifiers import ID_KEY_KEY, ID_TYPE_KEY, ranked_id_sources
from comicbox.identifiers.identifiers import (
    IDENTIFIER_PARTS_MAP,
    create_identifier,
    get_id_source_from_url,
)
from comicbox.identifiers.urns import (
    parse_string_identifier,
    to_urn_string,
)

PRIMARY_ID_SOURCE_KEYPATH = PRIMARY_ID_SOURCE_KEY


def _identifier_to_cb(native_identifier: str, naked_id_source: Any) -> tuple[str, dict]:
    """Parse one identifier urn or string."""
    id_source, id_type, id_key = parse_string_identifier(
        native_identifier, naked_id_source
    )
    id_source_str = id_source.value if id_source else ""
    comicbox_identifier = create_identifier(
        id_source_str, id_key, id_type=id_type, default_id_source_str=naked_id_source
    )
    return id_source_str, comicbox_identifier


def identifiers_to_cb(native_identifiers: Any, naked_id_source: Any) -> dict:
    """Parse identifier struct from a string or sequence."""
    comicbox_identifiers = {}
    if isinstance(native_identifiers, str):
        # A single-valued tag, like CoMet's <identifier>. Iterating the
        # string itself would parse it one character at a time.
        native_identifiers = (native_identifiers,)
    if native_identifiers:
        for native_identifier in native_identifiers:
            try:
                id_source_str, identifier = _identifier_to_cb(
                    native_identifier, naked_id_source
                )
                comicbox_identifiers[id_source_str] = identifier
            except Exception as exc:
                logger.warning(f"Parsing identifier {native_identifier}: {exc}")
    return comicbox_identifiers


def identifiers_transform_to_cb(
    identifiers_tag: str, naked_id_source: IdSources
) -> MetaSpec:
    """Transform identifier tags to comicbox identifiers."""

    def to_cb(native_identifiers: Any) -> dict[str, dict[str, str]]:
        return identifiers_to_cb(native_identifiers, naked_id_source)

    return MetaSpec(
        key_map={IDENTIFIERS_KEY: identifiers_tag},
        spec=to_cb,
    )


def _identifier_from_cb(comicbox_identifiers: dict[str, dict[str, str]]) -> str:
    """Unparse the best identifier to a single urn string."""
    for id_source_str in ranked_id_sources(comicbox_identifiers):
        if (
            (comicbox_identifier := comicbox_identifiers.get(id_source_str))
            and (id_key := comicbox_identifier.get(ID_KEY_KEY))
            and (
                urn_str := to_urn_string(
                    id_source_str, comicbox_identifier.get(ID_TYPE_KEY, ""), id_key
                )
            )
        ):
            return urn_str
    return ""


def identifier_transform_from_cb(identifier_tag: str) -> MetaSpec:
    """
    Transform comicbox identifiers to one identifier tag.

    For a format like CoMet that allows a single identifier, the best ranked
    source wins.
    """
    return MetaSpec(
        key_map={identifier_tag: IDENTIFIERS_KEY},
        spec=_identifier_from_cb,
    )


def identifier_from_url(url_str: str) -> tuple[str, dict]:
    """
    Parse an identifier out of a url comicbox recognizes.

    Returns an empty result for a url from a database comicbox doesn't know.
    Such a url is still kept verbatim in ``urls``; inventing an identifier
    source from its hostname only produced keys nothing could look up.
    """
    if not url_str:
        return "", {}
    id_source_str = get_id_source_from_url(url_str)
    if not id_source_str:
        return "", {}
    id_parts = IDENTIFIER_PARTS_MAP.get(IdSources(id_source_str))
    if not id_parts:
        return "", {}
    id_type, id_key = id_parts.parse_url_path(url_str)
    identifier = create_identifier(id_source_str, id_key, id_type=id_type)
    if not identifier.get(ID_KEY_KEY):
        return "", {}
    return id_source_str, identifier


def urls_to_cb(native_urls: Any) -> list[str]:
    """Collect url tags verbatim, in order, without duplicates."""
    urls: dict[str, None] = {}
    if isinstance(native_urls, str):
        native_urls = (native_urls,)
    if native_urls:
        for native_url in native_urls:
            if url_str := get_cdata(native_url):
                urls[str(url_str)] = None
    return list(urls)


def urls_transform_to_cb(urls_tag: str) -> MetaSpec:
    """Transform url tags to comicbox urls."""
    return MetaSpec(key_map={URLS_KEY: urls_tag}, spec=urls_to_cb)


def urls_transform_from_cb(urls_tag: str) -> MetaSpec:
    """Transform comicbox urls to url tags."""
    return MetaSpec(key_map={urls_tag: URLS_KEY}, spec=urls_to_cb)
