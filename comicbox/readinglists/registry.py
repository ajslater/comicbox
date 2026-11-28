"""
Reading-list format registry and content detection.

A registry of its own, apart from ``MetadataFormats``: that enum's order is
the masking order for comic metadata and its keys are collision-checked
against every comic format, where ``cbl``, ``json`` and ``yaml`` are taken.
Within reading lists those tokens are free.
"""

import codecs
import re
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any

import simplejson
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    Event,
    MappingStartEvent,
    ScalarEvent,
)

from comicbox.exceptions import ReadingListFormatError
from comicbox.readinglists.formats.cbl import CBL_REGISTRATION
from comicbox.readinglists.formats.cbl.schema import READING_LIST_TAG
from comicbox.readinglists.formats.json_cbl import JSON_CBL_REGISTRATION
from comicbox.readinglists.formats.json_cbl.schema import (
    FILE_DETAILS_KEY,
    ISSUE_LIST_KEY,
)
from comicbox.readinglists.formats.native import (
    JSON_REGISTRATION,
    YAML_REGISTRATION,
)
from comicbox.readinglists.schema import READING_LIST_KEY


class ReadingListFormats(Enum):
    """Reading-list file formats."""

    YAML = YAML_REGISTRATION
    JSON = JSON_REGISTRATION
    CBL = CBL_REGISTRATION
    JSON_CBL = JSON_CBL_REGISTRATION


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


def get_format(fmt: ReadingListFormats | str | None) -> ReadingListFormats:
    """Resolve a format token such as ``yaml``, or pass a member through."""
    if isinstance(fmt, ReadingListFormats):
        return fmt
    if isinstance(fmt, str) and (member := _TOKEN_MAP.get(fmt.strip().lower())):
        return member
    tokens = ", ".join(sorted(_TOKEN_MAP))
    reason = f"Unknown reading-list format {fmt!r}. Known formats: {tokens}."
    raise ReadingListFormatError(reason)


# What may come before an XML document's first element, and what ends it.
_XML_PROLOG = (("<?", "?>"), ("<!--", "-->"), ("<!DOCTYPE", ">"))
_XML_NAME_RE = re.compile(r"<([A-Za-z_][\w.:-]*)")
# XML root element -> format.
_XML_ROOTS: MappingProxyType[str, ReadingListFormats] = MappingProxyType(
    {READING_LIST_TAG: ReadingListFormats.CBL}
)
# Keys a JSON or YAML document's top level must hold, checked in order.
_JSON_SIGNATURES: tuple[tuple[frozenset[str], ReadingListFormats], ...] = (
    (frozenset({FILE_DETAILS_KEY, ISSUE_LIST_KEY}), ReadingListFormats.JSON_CBL),
    (frozenset({READING_LIST_KEY}), ReadingListFormats.JSON),
)
_YAML_SIGNATURES: tuple[tuple[frozenset[str], ReadingListFormats], ...] = (
    (frozenset({READING_LIST_KEY}), ReadingListFormats.YAML),
)


# Byte order marks and their codecs, UTF-32 first: its little-endian mark
# begins with UTF-16's.
_BOMS = (
    ((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE), "utf-32"),
    ((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE), "utf-16"),
)


def text_codec(data: bytes | bytearray) -> str:
    """Name the codec bytes are in: UTF-32 or UTF-16 by their mark, else UTF-8."""
    for marks, codec in _BOMS:
        if data.startswith(marks):
            return codec
    return "utf-8-sig"


def as_text(data: str | bytes | bytearray) -> str:
    """Decode bytes, dropping a byte order mark."""
    if isinstance(data, bytes | bytearray):
        return bytes(data).decode(text_codec(data), errors="replace")
    return data.removeprefix("\ufeff")


def _parse_json(text: str) -> Any:
    try:
        return simplejson.loads(text)
    except (ValueError, RecursionError):
        return None


# Deeper than any reading list, and than the YAML loader itself could build.
# The pure parser slows with each level, so the scan stops here.
_YAML_MAX_DEPTH = 1000


class _RootKeys:
    """Collect the scalar keys of a YAML root mapping from its events."""

    __slots__ = ("depth", "done", "is_key", "keys")

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.depth = 0
        self.is_key = True
        self.done = False

    def feed(self, event: Event) -> bool:
        """Take one event; False when the root is no mapping or is too deep."""
        if isinstance(event, CollectionStartEvent):
            return self._start(event)
        if isinstance(event, CollectionEndEvent):
            self.depth -= 1
            self.done = self.depth == 0
        elif isinstance(event, ScalarEvent | AliasEvent):
            return self._node(event)
        return True

    def _start(self, event: CollectionStartEvent) -> bool:
        if self.depth == 0 and not isinstance(event, MappingStartEvent):
            return False
        if self.depth == 1:
            self.is_key = not self.is_key
        self.depth += 1
        return self.depth <= _YAML_MAX_DEPTH

    def _node(self, event: ScalarEvent | AliasEvent) -> bool:
        if self.depth == 0:
            return False
        if self.depth == 1:
            if self.is_key and isinstance(event, ScalarEvent):
                self.keys.add(event.value)
            self.is_key = not self.is_key
        return True


def _yaml_keys(text: str) -> frozenset[str] | None:
    """
    Read the scalar keys of a YAML document's root mapping from its events.

    Nothing is built: one pass over the parser's events, as the alias check
    makes. None when the root is not a mapping, the text is not YAML, or it
    nests deeper than ``_YAML_MAX_DEPTH``.
    """
    root = _RootKeys()
    try:
        for event in YAML(typ="safe", pure=True).parse(text):
            if not root.feed(event):
                return None
            if root.done:
                break
    except (YAMLError, RecursionError):
        return None
    return frozenset(root.keys)


def _match_keys(
    keys: frozenset[str] | None,
    signatures: tuple[tuple[frozenset[str], ReadingListFormats], ...],
) -> ReadingListFormats | None:
    if keys is None:
        return None
    for required, member in signatures:
        if required <= keys:
            return member
    return None


def _match_signature(
    document: Any,
    signatures: tuple[tuple[frozenset[str], ReadingListFormats], ...],
) -> ReadingListFormats | None:
    if not isinstance(document, Mapping):
        return None
    return _match_keys(frozenset(document), signatures)


def _prolog_end(text: str, start: int, closer: str) -> int:
    """
    Find where a prolog part ends, past a DOCTYPE's internal subset.

    ``<!DOCTYPE x [<!ENTITY y "z">]>`` ends at the ``>`` after its ``]``,
    not at the first ``>``. Each find starts past the last, so the scan
    stays linear.
    """
    end = text.find(closer, start)
    if closer == ">" and end >= 0 and (bracket := text.find("[", start, end)) >= 0:
        close = text.find("]", bracket)
        end = -1 if close < 0 else text.find(closer, close)
    return end


def xml_root(text: str) -> str | None:
    """
    Name an XML document's first element, past its declaration and comments.

    A scan, not one pattern: each part of the prolog is skipped by finding
    its end, so the time is linear in the text however it is built.
    """
    position, size, skipped = 0, len(text), True
    while skipped:
        while position < size and text[position].isspace():
            position += 1
        skipped = False
        for opener, closer in _XML_PROLOG:
            if text.startswith(opener, position):
                end = _prolog_end(text, position + len(opener), closer)
                if end < 0:
                    return None
                position, skipped = end + len(closer), True
                break
    match = _XML_NAME_RE.match(text, position)
    return match.group(1) if match else None


def detect_format(data: str | bytes | bytearray) -> ReadingListFormats | None:
    """
    Detect a reading list's format by its content, not its file name.

    XML by its root element; JSON and YAML by their top-level keys. JSON is
    tried before YAML, since every JSON document is also YAML.
    """
    text = as_text(data)
    if not text.strip():
        return None
    if (root := xml_root(text)) is not None:
        return _XML_ROOTS.get(root)
    if (document := _parse_json(text)) is not None:
        return _match_signature(document, _JSON_SIGNATURES)
    return _match_keys(_yaml_keys(text), _YAML_SIGNATURES)
