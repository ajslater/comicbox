"""
lost_fields is exact: it names what a round trip changes, and nothing else.

The expected answer is worked out here independently: write the list, read
it back, flatten both and compare, path by path.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    ReadingListFormats,
    dumps,
    load,
    loads,
    lost_fields,
)
from comicbox.readinglists.serialize import load_model
from tests.const import TEST_FILES_DIR

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
_FIXTURES = (
    READING_LISTS_DIR / "civil-war.yaml",
    READING_LISTS_DIR / "cbl" / "common.cbl",
    READING_LISTS_DIR / "cbl" / "two-databases.cbl",
    READING_LISTS_DIR / "cbl" / "comicrack-native.cbl",
    READING_LISTS_DIR / "json-cbl" / "full.json",
    READING_LISTS_DIR / "json-cbl" / "minimal.json",
)
_DEFAULTS = {"ordered": True, "private": False}
_ID_PARTS = 2  # "identifiers.<source>" is the finest an id is named


def _flatten(value: Any, path: tuple[str, ...]) -> dict[tuple[str, ...], Any]:
    if isinstance(value, Mapping) and value:
        flat: dict[tuple[str, ...], Any] = {}
        for key, item in value.items():
            flat.update(_flatten(item, (*path, str(key))))
        return flat
    return {path: value}


def _named(path: tuple[str, ...]) -> str:
    """Cut a path to the depth lost_fields names: an identifier whole."""
    if "identifiers" in path:
        cut = path.index("identifiers") + _ID_PARTS
        path = path[:cut]
    return ".".join(path)


def _entry_names(kept: list[dict[str, Any]], back: list[dict[str, Any]]) -> set[str]:
    assert len(kept) == len(back)
    names = set()
    for entry, entry_back in zip(kept, back, strict=True):
        flat, flat_back = (
            _flatten(entry, ("entries",)),
            _flatten(entry_back, ("entries",)),
        )
        names |= {
            _named(path)
            for path in set(flat) | set(flat_back)
            if flat.get(path) != flat_back.get(path)
        }
    return names


def _header_names(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    header = {**_DEFAULTS, **before}
    header_back = {**_DEFAULTS, **after}
    header.pop(ENTRIES_KEY, None)
    header_back.pop(ENTRIES_KEY, None)
    return {
        key
        for key in set(header) | set(header_back)
        if header.get(key) != header_back.get(key)
    }


def _skipped(lost: tuple[str, ...]) -> list[int]:
    """Read the entries lost_fields says are not written, from 0."""
    for item in lost:
        if item.startswith("entries #"):
            return [
                int(part.strip()[1:]) - 1 for part in item[len("entries ") :].split(",")
            ]
    return []


def _check(reading_list: Mapping[str, Any], fmt: ReadingListFormats) -> None:
    before = load_model(reading_list)
    after = loads(dumps(before, fmt), fmt=fmt).reading_list
    lost = lost_fields(before, fmt)
    skipped = _skipped(lost)
    kept = [
        entry
        for position, entry in enumerate(before.get(ENTRIES_KEY) or [])
        if position not in skipped
    ]
    expected = _header_names(before, after) | _entry_names(
        kept, after.get(ENTRIES_KEY) or []
    )
    named = {item for item in lost if not item.startswith("entries #")}
    assert named == expected


@pytest.mark.parametrize("fmt", list(ReadingListFormats), ids=lambda fmt: fmt.name)
@pytest.mark.parametrize("path", _FIXTURES, ids=lambda path: path.name)
def test_fixtures(path: Any, fmt: ReadingListFormats) -> None:
    _check(load(path).reading_list, fmt)


# Plain names, and the ones outside text brings: control characters, markup,
# a CDATA end, zero-width and combining characters, an emoji, padding.
_WORDS = (
    "Civil War",
    "Pokémon",
    "X-Men",
    "ワンピース",
    "Batman",
    "a\x1b[0m",
    "Tom & Jerry <b>meet</b>",
    "]]> & <!--",
    "zero\u200bwidth",
    "e\u0301 combined",
    "😀 Emoji",
    "tab\tand\nnewline",
    "  padded  ",
    "bell\x07 and \x7f del",
)
_SOURCES = ("comicvine", "metron", "grandcomicsdatabase", "isbn", "upc", "marvel")


def _maybe(rng: random.Random, value: Any, chance: float = 0.5) -> Any:
    return value if rng.random() < chance else None


def _series(rng: random.Random) -> dict[str, Any]:
    return {
        "name": rng.choice(_WORDS),
        "start_year": _maybe(rng, rng.choice((1850, 1963, 2006, 2099, 2150))),
        "end_year": _maybe(rng, 2008, 0.2),
        "sort_name": _maybe(rng, "sort", 0.2),
        "summary": _maybe(rng, "About it.", 0.2),
        "volume_count": _maybe(rng, 3, 0.2),
        "alternative_names": _maybe(rng, [{"name": "Other"}], 0.2),
        "identifiers": _maybe(rng, _ids(rng)),
    }


def _ids(rng: random.Random) -> dict[str, Any]:
    return {
        source: {"key": str(rng.randint(1, 9999))}
        for source in rng.sample(_SOURCES, rng.randint(1, 3))
    }


def _date(rng: random.Random) -> dict[str, Any]:
    day = date(2000, 1, 1) + timedelta(days=rng.randint(0, 9000))
    return {
        "cover_date": _maybe(rng, day),
        "store_date": _maybe(rng, day, 0.3),
        "year": _maybe(rng, day.year),
        "month": _maybe(rng, day.month, 0.3),
        "day": _maybe(rng, day.day, 0.2),
    }


def _entry(rng: random.Random) -> dict[str, Any]:
    issue = {"name": rng.choice(("1", "2AU", "-1", "½", "Annual"))}
    if rng.random() < 0.2:
        issue = {"number": rng.randint(1, 50)}
    return {
        "series": _maybe(rng, _series(rng), 0.9),
        "volume": _maybe(
            rng, {"number": rng.choice((1, 2006)), "issue_count": _maybe(rng, 12)}
        ),
        "issue": _maybe(rng, issue, 0.9),
        "date": _maybe(rng, _date(rng), 0.8),
        "identifiers": _maybe(rng, _ids(rng)),
        "entry_type": _maybe(rng, rng.choice(("core", "tie-in", "prologue"))),
        "notes": _maybe(rng, rng.choice(("Read this.", *_WORDS)), 0.2),
    }


def _header(rng: random.Random) -> dict[str, Any]:
    sources = [
        {"kind": "json-cbl", "key": "k1", "curator": rng.choice(("mg", "Some Site"))},
        {"kind": "metron-list", "key": "12", "url": "https://metron.cloud/x"},
        {"kind": "file", "curator": "cbro", "curator_url": "ftp://not-http"},
        {"kind": "tags"},
    ]
    return {
        "name": _maybe(rng, rng.choice(("A List", *_WORDS)), 0.9),
        "description": _maybe(rng, rng.choice(("About.", *_WORDS))),
        "list_type": _maybe(rng, rng.choice(("event", "story", "teams", "creator"))),
        "ordered": _maybe(rng, rng.random() < 0.5),
        "start_year": _maybe(rng, rng.choice((1890, 2006))),
        "end_year": _maybe(rng, 2007),
        "private": _maybe(rng, rng.random() < 0.5),
        "sources": _maybe(rng, rng.sample(sources, rng.randint(1, 3))),
        "previous": _maybe(rng, {"name": "Before", "kind": "json-cbl", "key": "u1"}),
        "next": _maybe(rng, {"name": "After", "kind": "metron-list", "key": "13"}),
        "tags": _maybe(rng, {"Crossover", "marvel"}),
        "notes": _maybe(rng, "Notes."),
    }


def _random_list(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)  # noqa: S311 - a test fixture, not a secret
    entries = [_entry(rng) for _ in range(rng.randint(1, 8))]
    return {**_header(rng), ENTRIES_KEY: entries}


@pytest.mark.parametrize("fmt", list(ReadingListFormats), ids=lambda fmt: fmt.name)
@pytest.mark.parametrize("seed", range(30))
def test_generated_lists(seed: int, fmt: ReadingListFormats) -> None:
    _check(_random_list(seed), fmt)


def test_unwritable_entries_are_named_by_position() -> None:
    reading_list = {
        "name": "A",
        "sources": [{"kind": "file"}],
        ENTRIES_KEY: [
            {"series": {"name": "A"}, "issue": {"name": "1"}},
            {"series": {"name": "A"}},
            {"issue": {"name": "2"}},
        ],
    }
    assert lost_fields(reading_list, "cbl") == ("entries #2, #3",)
