"""
Reading-list format registry and content detection.

A registry of its own, apart from ``MetadataFormats``: that enum's order is
the masking order for comic metadata and its keys are collision-checked
against every comic format, where ``cbl``, ``json`` and ``yaml`` are taken.
Within reading lists those tokens are free.
"""

import re
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any

import simplejson
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from comicbox.exceptions import ReadingListFormatError
from comicbox.readinglists.formats.native import (
    JSON_REGISTRATION,
    YAML_REGISTRATION,
)
from comicbox.readinglists.schema import READING_LIST_KEY


class ReadingListFormats(Enum):
    """Reading-list file formats."""

    YAML = YAML_REGISTRATION
    JSON = JSON_REGISTRATION


def _build_token_map() -> MappingProxyType[str, ReadingListFormats]:
    """Map every token to its format; fail at import on a collision."""
    token_map: dict[str, ReadingListFormats] = {}
    for member in ReadingListFormats:
        for token in member.value.tokens:
            if (other := token_map.get(token)) is not None:
                reason = (
                    f"reading-list format token {token!r} is claimed by both"
                    f" {other.name} and {member.name}"
                )
                raise RuntimeError(reason)
            token_map[token] = member
    return MappingProxyType(token_map)


_TOKEN_MAP = _build_token_map()


def get_format(fmt: ReadingListFormats | str) -> ReadingListFormats:
    """Resolve a format token such as ``yaml``, or pass a member through."""
    if isinstance(fmt, ReadingListFormats):
        return fmt
    if member := _TOKEN_MAP.get(fmt.strip().lower()):
        return member
    tokens = ", ".join(sorted(_TOKEN_MAP))
    reason = f"Unknown reading-list format {fmt!r}. Known formats: {tokens}."
    raise ReadingListFormatError(reason)


# The first element's name, past an XML declaration, comments and a doctype.
_XML_ROOT_RE = re.compile(
    r"\A\s*(?:<\?.*?\?>\s*)?(?:(?:<!--.*?-->|<!DOCTYPE[^>]*>)\s*)*<([A-Za-z_][\w.:-]*)",
    re.DOTALL,
)
# XML root element -> format.
_XML_ROOTS: MappingProxyType[str, ReadingListFormats] = MappingProxyType({})
# Keys a JSON or YAML document's top level must hold, checked in order.
_JSON_SIGNATURES: tuple[tuple[frozenset[str], ReadingListFormats], ...] = (
    (frozenset({READING_LIST_KEY}), ReadingListFormats.JSON),
)
_YAML_SIGNATURES: tuple[tuple[frozenset[str], ReadingListFormats], ...] = (
    (frozenset({READING_LIST_KEY}), ReadingListFormats.YAML),
)


def as_text(data: str | bytes | bytearray) -> str:
    """Decode bytes, dropping a byte order mark."""
    if isinstance(data, bytes | bytearray):
        return bytes(data).decode("utf-8-sig", errors="replace")
    return data.removeprefix("﻿")


def _parse_json(text: str) -> Any:
    try:
        return simplejson.loads(text)
    except ValueError:
        return None


def _parse_yaml(text: str) -> Any:
    try:
        return YAML(typ="safe", pure=True).load(text)
    except YAMLError:
        return None


def _match_signature(
    document: Any,
    signatures: tuple[tuple[frozenset[str], ReadingListFormats], ...],
) -> ReadingListFormats | None:
    if not isinstance(document, Mapping):
        return None
    keys = frozenset(document)
    for required, member in signatures:
        if required <= keys:
            return member
    return None


def detect_format(data: str | bytes | bytearray) -> ReadingListFormats | None:
    """
    Detect a reading list's format by its content, not its file name.

    XML by its root element; JSON and YAML by their top-level keys. JSON is
    tried before YAML, since every JSON document is also YAML.
    """
    text = as_text(data)
    if not text.strip():
        return None
    if match := _XML_ROOT_RE.match(text):
        return _XML_ROOTS.get(match.group(1))
    if (document := _parse_json(text)) is not None:
        return _match_signature(document, _JSON_SIGNATURES)
    return _match_signature(_parse_yaml(text), _YAML_SIGNATURES)
