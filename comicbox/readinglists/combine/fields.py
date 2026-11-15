"""
Merge the fields of the rows in a group, and the lists' headers.

First wins, in rank order. The model drops empty values on load, so the
first value present is the first non-empty one. ``mergedeep`` has no
first-wins strategy, and a reversed replace would recurse past the one
level these rules stop at, mixing two sources' identifier values.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from comicbox.empty import is_empty
from comicbox.readinglists.schema import (
    DATE_KEY,
    DESCRIPTION_KEY,
    END_YEAR_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    NEXT_KEY,
    NOTES_KEY,
    ORDERED_KEY,
    PREVIOUS_KEY,
    PRIVATE_KEY,
    SERIES_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCES_KEY,
    START_YEAR_KEY,
    TAGS_KEY,
    VOLUME_KEY,
)

# Merged leaf by leaf, one level down.
_NESTED_KEYS = frozenset({DATE_KEY, ISSUE_KEY, SERIES_KEY, VOLUME_KEY})
# Taken whole from the first input that has them.
_FIRST_HEADER_KEYS = (
    DESCRIPTION_KEY,
    LIST_TYPE_KEY,
    START_YEAR_KEY,
    END_YEAR_KEY,
    PRIVATE_KEY,
    PREVIOUS_KEY,
    NEXT_KEY,
    NOTES_KEY,
)


def is_ordered(reading_list: Mapping[str, Any]) -> bool:
    """Whether a list's order is authoritative: unless it says it is not."""
    return reading_list.get(ORDERED_KEY) is not False


def _union_ids(
    dest: Mapping[str, Any] | None, source: Mapping[str, Any]
) -> dict[str, Any]:
    """Union identifiers; the first value per database wins."""
    result = dict(dest or {})
    for id_source, identifier in source.items():
        result.setdefault(id_source, identifier)
    return result


def _merge_one_level(dest: Mapping[str, Any], source: Mapping[str, Any]) -> dict:
    result = dict(dest)
    for key, value in source.items():
        if key == IDENTIFIERS_KEY:
            result[key] = _union_ids(result.get(key), value)
        else:
            result.setdefault(key, value)
    return result


def merge_entry(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge the rows of one group, in rank order."""
    merged: dict[str, Any] = {}
    for entry in entries:
        for key, value in entry.items():
            if key == IDENTIFIERS_KEY:
                merged[key] = _union_ids(merged.get(key), value)
            elif key in _NESTED_KEYS and isinstance(value, Mapping):
                merged[key] = _merge_one_level(merged.get(key) or {}, value)
            else:
                merged.setdefault(key, value)
    return merged


def merge_sources(reading_lists: Sequence[Mapping[str, Any]]) -> list[dict]:
    """
    Concatenate the lists' sources in rank order.

    Two with the same kind and key are one, first value per field, so a
    pointer to an arc and the arc fetched from there collapse into the
    fetched one. Sources without a key are kept apart unless equal: two CBL
    files with different curators are two sources.
    """
    merged: list[dict] = []
    keyed: dict[tuple[Any, Any], int] = {}
    for reading_list in reading_lists:
        for source in reading_list.get(SOURCES_KEY) or ():
            if not (key := source.get(SOURCE_KEY_KEY)):
                if source not in merged:
                    merged.append(dict(source))
                continue
            identity = (source.get(SOURCE_KIND_KEY), key)
            if (index := keyed.get(identity)) is None:
                keyed[identity] = len(merged)
                merged.append(dict(source))
            else:
                merged[index] = {**source, **merged[index]}
    return merged


def _first(reading_lists: Sequence[Mapping[str, Any]], key: str) -> Any:
    """Get a key's value from the first list that has it."""
    return next((rl[key] for rl in reading_lists if key in rl), None)


def merge_header(
    reading_lists: Sequence[Mapping[str, Any]], backbone: int | None
) -> dict[str, Any]:
    """Merge the lists' headers, in rank order. The name is the backbone's."""
    by_name = list(reading_lists)
    if backbone is not None:
        by_name.insert(0, by_name.pop(backbone))
    values = {NAME_KEY: _first(by_name, NAME_KEY)}
    values.update({key: _first(reading_lists, key) for key in _FIRST_HEADER_KEYS})
    if any(ORDERED_KEY in reading_list for reading_list in reading_lists):
        values[ORDERED_KEY] = any(map(is_ordered, reading_lists))
    values[SOURCES_KEY] = merge_sources(reading_lists)
    values[TAGS_KEY] = set().union(*(rl.get(TAGS_KEY) or () for rl in reading_lists))
    return {key: value for key, value in values.items() if not is_empty(value)}
