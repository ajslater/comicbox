"""
Text from outside, made safe once.

A reading list's strings come from files and from the network. Control
characters in them can make a CBL that XML cannot read back, or reach a
terminal as escape sequences, so they are removed when a list is loaded,
with a warning naming where.
"""

import re
from collections.abc import Mapping
from typing import Any

# C0 but tab, newline and carriage return; DEL and C1; the two
# noncharacters at the end of the BMP; and surrogates, which in a str are
# always lone ones. XML 1.0 allows none of them.
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f￾￿\ud800-\udfff]")
# What a terminal line must not hold either: it would start another line.
_LINE_BREAK_RE = re.compile(r"[\t\n\r]+")


def clean_text(text: str) -> str:
    """Remove control characters a list's text may not hold."""
    return _CONTROL_RE.sub("", text)


def printable(text: str) -> str:
    """Make outside text safe for one terminal line."""
    return _LINE_BREAK_RE.sub(" ", clean_text(text))


def _join(path: str, key: Any) -> str:
    return f"{path}.{key}" if path else str(key)


def clean_tree(value: Any, warnings: list[str], path: str = "") -> Any:
    """
    Remove control characters from every string in a parsed list.

    Each string that loses any is named in ``warnings`` by its path, as the
    load's other warnings are: ``name``, ``entries #3.series.name``.
    """
    if isinstance(value, str):
        cleaned = clean_text(value)
        if cleaned != value:
            warnings.append(f"{path or 'text'}: control characters removed")
        return cleaned
    if isinstance(value, Mapping):
        return {
            key: clean_tree(item, warnings, _join(path, key))
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [
            clean_tree(item, warnings, f"{path} #{position}")
            for position, item in enumerate(value, start=1)
        ]
    if isinstance(value, set | frozenset):
        return {clean_tree(item, warnings, path) for item in value}
    return value
