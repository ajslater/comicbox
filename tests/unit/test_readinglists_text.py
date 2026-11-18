"""Text from outside is cleaned once, at the model, and printed safely."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from comicbox.readinglists import (
    MetronListSummary,
    ReadingListFormats,
    dumps,
    load,
    loads,
    lost_fields,
)
from comicbox.readinglists.render import print_error, print_metron_lists
from comicbox.readinglists.text import printable

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_NOT_UTF8 = "text: not valid UTF-8; the bytes that are not were replaced with U+FFFD"


# ----------------------------------------------------- control characters


@pytest.mark.parametrize(
    "bad",
    ["\x00", "\x1b", "\x07", "\x7f", "\x85", "\x9b", "￾", "￿", "\ud800"],
    ids=["nul", "esc", "bell", "del", "c1-nel", "c1-csi", "fffe", "ffff", "surrogate"],
)
def test_control_characters_are_removed_with_a_warning(bad: str) -> None:
    result = loads(_json_with(bad))
    assert result.reading_list["name"] == "Civil War"
    assert result.reading_list["entries"][0]["series"]["name"] == "X-Men"
    assert "name: control characters removed" in result.warnings
    assert "entries #1.series.name: control characters removed" in result.warnings


def _json_with(bad: str) -> str:
    """Build JSON, which can carry any of them as an escape."""
    escape = f"\\u{ord(bad):04x}"
    return (
        '{"reading_list": {"name": "Civil' + escape + ' War", "entries": '
        '[{"series": {"name": "X' + escape + '-Men"}, "issue": {"name": "1"}}]}}'
    )


def test_tab_newline_and_return_are_kept() -> None:
    result = loads('{"reading_list": {"name": "A", "description": "a\\tb\\nc\\rd"}}')
    assert result.reading_list["description"] == "a\tb\nc\rd"
    assert result.warnings == ()


@pytest.mark.parametrize("fmt", list(ReadingListFormats), ids=lambda fmt: fmt.name)
def test_a_name_with_an_escape_sequence_round_trips(fmt: ReadingListFormats) -> None:
    """It made a CBL that XML could not read back, and lost_fields raised."""
    reading_list = {
        "name": "a\x1b[0m list",
        "entries": [
            {
                "series": {"name": "b\x1b[2J", "start_year": 2006},
                "issue": {"name": "1"},
                "date": {"cover_date": "2006-07-01", "year": 2006},
            }
        ],
    }
    text = dumps(reading_list, fmt)
    assert "\x1b" not in text
    assert loads(text, fmt=fmt).reading_list["name"] == "a[0m list"
    lost_fields(reading_list, fmt)


# ------------------------------------------------------------------- tags


def test_tags_that_are_not_strings_are_dropped() -> None:
    result = loads("reading_list:\n  name: A\n  tags: [{k: v}, [x], ok, 7]\n")
    assert result.reading_list["tags"] == {"ok"}
    assert "tags: {'k': 'v'} is not a string; dropped" in result.warnings
    assert "tags: ['x'] is not a string; dropped" in result.warnings
    assert "tags: 7 is not a string; dropped" in result.warnings


# ------------------------------------------------------------------ bytes


_LATIN_CBL = (
    '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
    "<ReadingList><Name>Pokémon</Name><Books>"
    '<Book Series="Pokémon" Number="1" Volume="1998" Year="1999" />'
    "</Books></ReadingList>"
).encode("latin-1")


def test_xml_is_read_in_the_encoding_it_declares(tmp_path: Path) -> None:
    path = tmp_path / "latin.cbl"
    path.write_bytes(_LATIN_CBL)
    for result in (loads(_LATIN_CBL), load(path)):
        assert result.reading_list["name"] == "Pokémon"
        assert result.reading_list["entries"][0]["series"]["name"] == "Pokémon"
        assert result.warnings == ()


def test_undeclared_latin_1_xml_is_read_with_a_warning() -> None:
    undeclared = _LATIN_CBL.replace(b' encoding="ISO-8859-1"', b"")
    result = loads(undeclared)
    assert result.reading_list["name"] == "Pok�mon"
    assert _NOT_UTF8 in result.warnings


@pytest.mark.parametrize(
    "data",
    [
        b"reading_list:\n  name: Pok\xe9mon\n",
        b'{"reading_list": {"name": "Pok\xe9mon"}}',
    ],
    ids=["yaml", "json"],
)
def test_bytes_that_are_not_utf_8_are_a_warning(data: bytes) -> None:
    result = loads(data)
    assert result.reading_list["name"] == "Pok�mon"
    assert _NOT_UTF8 in result.warnings


def test_utf_8_bytes_with_a_bom_are_read_quietly() -> None:
    result = loads("﻿reading_list:\n  name: Pokémon\n".encode())
    assert result.reading_list["name"] == "Pokémon"
    assert result.warnings == ()


# ---------------------------------------------------------------- printing


def _printed(write: Callable[[Console], None]) -> str:
    console = Console(file=None, highlight=False, record=True, width=200)
    write(console)
    return console.export_text()


def test_the_metron_table_prints_no_escape_sequence() -> None:
    found = MetronListSummary(
        id=1,
        name="Clear\x1b[2J screen",
        list_type="Event\x1b[31m",
        private=False,
        curator=None,
        username="user\x07",
        rating=None,
        rating_count=0,
        modified=datetime(2024, 1, 1, tzinfo=UTC),
    )
    text = _printed(lambda console: print_metron_lists(console, [found]))
    assert "\x1b" not in text
    assert "\x07" not in text
    assert "Clear[2J screen" in text


def test_an_error_line_prints_no_escape_or_line_break() -> None:
    error = ValueError("bad\x1b[2J\nfake: second line")
    text = _printed(lambda console: print_error(console, "list\x1b.cbl", error))
    assert "\x1b" not in text
    assert text.count("\n") == 1


def test_printable_folds_line_breaks() -> None:
    assert printable("a\tb\nc\r\nd\x1b") == "a b c d"
