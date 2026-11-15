"""
Name what a load dropped or changed, by comparing its input and output.

One mechanism for every kind of loss: an unknown key, an invalid value, a
structure where a scalar belongs, a clamped number. A value equal in
meaning, such as ``1`` read as ``"1"``, ``Event`` read as ``event`` or a
list of tags read as a set, is not a change.
"""

import reprlib
from collections.abc import Collection, Iterator, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from comicbox.empty import is_empty

_MAX_REPR = 60
# Bounds the work of quoting a value as well as its text. A plain repr of a
# list nested 200,000 deep takes seconds once the stack allows it to finish,
# as make's raised stack limit does.
_REPR = reprlib.Repr()
_REPR.maxlevel = 3
_REPR.maxdict = _REPR.maxlist = _REPR.maxtuple = _REPR.maxset = 6
_REPR.maxstring = _REPR.maxother = _MAX_REPR
_CDATA_KEY = "#text"
_NO_IGNORE: frozenset[str] = frozenset()
# Scalars compared by value rather than by their text.
_VALUE_TYPES = (date, Decimal, int, float)


def quote_value(value: Any) -> str:
    """Quote a value for a warning, cut to a bounded length."""
    text = _REPR.repr(value)
    return text if len(text) <= _MAX_REPR else text[: _MAX_REPR - 1] + "…"


_repr = quote_value


def _join(path: str, key: Any) -> str:
    return f"{path}.{key}" if path else str(key)


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _word(value: str) -> str:
    """Fold case and separators, as the vocabulary fields do."""
    return "-".join(value.casefold().replace("_", " ").split())


def _same_number(raw: Any, loaded: Any) -> bool:
    """Compare numbers by value, and a date with its ISO text."""
    if isinstance(raw, date) or isinstance(loaded, date):
        return str(raw).strip() == str(loaded)
    raw_number = _decimal(raw)
    return raw_number is not None and raw_number == _decimal(loaded)


def _same(raw: Any, loaded: Any) -> bool:
    """Whether a loaded scalar means what the raw one did."""
    raw = raw.value if isinstance(raw, Enum) else raw
    loaded = loaded.value if isinstance(loaded, Enum) else loaded
    if isinstance(raw, bool) or isinstance(loaded, bool):
        return str(raw).casefold() == str(loaded).casefold()
    if isinstance(raw, _VALUE_TYPES) or isinstance(loaded, _VALUE_TYPES):
        return _same_number(raw, loaded)
    if isinstance(raw, str) and isinstance(loaded, str):
        return _word(raw) == _word(loaded)
    return raw == loaded


def _set_changes(raw: Collection, loaded: Collection, path: str) -> Iterator[str]:
    """Name each member of a raw collection the loaded set lacks."""
    kept = {_word(str(item)) for item in loaded}
    for item in raw:
        if not is_empty(item) and _word(str(item)) not in kept:
            yield f"{path}: {_repr(item)} dropped"


# How far ahead of the last pairing a survivor is looked for: dropped items
# are few, and a bound keeps a long list with many of them linear.
_PAIRING_WINDOW = 16


def _matches(raw_item: Any, item: Any) -> bool:
    """Whether a loaded item plausibly came from a raw one."""
    if isinstance(raw_item, Mapping) and isinstance(item, Mapping):
        shared = [key for key in item if key in raw_item]
        return bool(shared) and any(
            _same(raw_item[key], item[key])
            for key in shared
            if not isinstance(item[key], Mapping | list | tuple | set | frozenset)
        )
    if isinstance(raw_item, Mapping) or isinstance(item, Mapping):
        return False
    return _same(raw_item, item)


def _pair(raw: list, loaded: list) -> list[tuple[int, Any, Any]]:
    """Pair each surviving item with the raw item it came from, in order."""
    pairs: list[tuple[int, Any, Any]] = []
    start = 0
    for item in loaded:
        if start >= len(raw):
            break
        window = range(start, min(len(raw), start + _PAIRING_WINDOW))
        index = next((i for i in window if _matches(raw[i], item)), start)
        pairs.append((index, raw[index], item))
        start = index + 1
    return pairs


def _list_changes(
    raw: list, loaded: list, path: str, ignore: frozenset[str]
) -> Iterator[str]:
    if len(raw) != len(loaded):
        # A list that drops empty items drops them silently, as a mapping
        # drops empty values; compare what is left.
        raw = [item for item in raw if not is_empty(item)]
        loaded = [item for item in loaded if not is_empty(item)]
    if len(raw) == len(loaded):
        pairs = [(index, raw[index], item) for index, item in enumerate(loaded)]
    else:
        yield f"{path}: {len(raw) - len(loaded)} of {len(raw)} items dropped"
        # What the survivors lost is still worth naming.
        pairs = _pair(raw, loaded)
    for index, raw_item, item in pairs:
        yield from describe_changes(raw_item, item, f"{path} #{index + 1}", ignore)


def _mapping_changes(
    raw: Mapping, loaded: Any, path: str, ignore: frozenset[str]
) -> Iterator[str]:
    if not isinstance(loaded, Mapping):
        if _CDATA_KEY in raw:
            yield from describe_changes(raw[_CDATA_KEY], loaded, path, ignore)
        elif isinstance(loaded, list) and len(loaded) == 1:
            yield from describe_changes(raw, loaded[0], path, ignore)
        else:
            yield f"{path}: {_repr(raw)} read as {_repr(loaded)}"
        return
    for key, value in raw.items():
        if key in ignore or is_empty(value):
            continue
        here = _join(path, key)
        if key in loaded:
            yield from describe_changes(value, loaded[key], here, ignore)
        elif isinstance(value, Mapping):
            # Name the leaves that were dropped, not the mapping they left.
            yield from _mapping_changes(value, {}, here, ignore)
        else:
            yield f"{here}: {_repr(value)} dropped"


def describe_changes(
    raw: Any, loaded: Any, path: str = "", ignore: frozenset[str] = _NO_IGNORE
) -> Iterator[str]:
    """
    Name every key or value in ``raw`` that ``loaded`` dropped or changed.

    ``path`` prefixes each message; list items are numbered from 1.
    ``ignore`` names keys a format leaves out on purpose.
    """
    if isinstance(raw, Mapping):
        yield from _mapping_changes(raw, loaded, path, ignore)
    elif isinstance(raw, list | tuple) and isinstance(loaded, set | frozenset):
        yield from _set_changes(raw, loaded, path)
    elif isinstance(raw, list | tuple) and isinstance(loaded, list | tuple):
        yield from _list_changes(list(raw), list(loaded), path, ignore)
    elif isinstance(raw, list | tuple) and len(raw) == 1:
        yield from describe_changes(raw[0], loaded, path, ignore)
    elif not _same(raw, loaded):
        yield f"{path}: {_repr(raw)} read as {_repr(loaded)}"
