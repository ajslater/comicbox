"""
Hostile documents: each is read, or refused in one line, in bounded time.

A fetched list is remote text, so detection and parsing must not hang on a
few hundred crafted bytes, nor turn them into gigabytes.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date
from typing import TYPE_CHECKING

import httpx
import pytest

from comicbox.readinglists import (
    ReadingListFormatError,
    ReadingListFormats,
    ReadingListSession,
    detect_format,
    dumps,
    load,
    loads,
)
from comicbox.readinglists.registry import xml_root
from comicbox.series_name import normalize_series

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@contextmanager
def _quickly(seconds: float = 1.0) -> Generator[None]:
    """Fail the block if it runs past ``seconds``."""
    started = time.monotonic()
    yield
    elapsed = time.monotonic() - started
    assert elapsed < seconds, f"took {elapsed:.2f}s"


# ------------------------------------------------------- linear detection


def test_many_comments_before_the_root_are_linear() -> None:
    """The old pattern doubled its time with each comment: 22 took 0.35 s."""
    text = "<!--x-->" * 5000 + "!"
    with _quickly():
        assert detect_format(text) is None
    with _quickly(), pytest.raises(ReadingListFormatError):
        loads(text)


@pytest.mark.parametrize(
    ("text", "root"),
    [
        ("<ReadingList/>", "ReadingList"),
        (
            '<?xml version="1.0"?>\n<!-- a -->\n<!DOCTYPE x>\n<ReadingList>',
            "ReadingList",
        ),
        ("  <!--a--><!--b--> <?pi x?><Other>", "Other"),
        ("<!-- never closed", None),
        ("<?xml never closed", None),
        ("not xml", None),
    ],
)
def test_the_root_scan(text: str, root: str | None) -> None:
    assert xml_root(text) == root


def test_a_long_run_of_spaces_in_a_series_name_is_linear() -> None:
    """The volume rule's leading whitespace run made this quadratic: 4.4 s."""
    with _quickly():
        assert normalize_series("a" + " " * 50_000 + "b") == "a b"


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("Bladehawk Vol. 2", "bladehawk"),
        ("Z-Men (Volume 3)", "z men"),
        ("Sonnet vol 1", "sonnet"),
        ("Revolution 2", "revolution 2"),
    ],
)
def test_the_volume_rule_is_unchanged(name: str, normalized: str) -> None:
    assert normalize_series(name) == normalized


# ----------------------------------------------------------- YAML aliases


def _doubling_aliases(levels: int) -> str:
    """Each anchor holds the last one twice: 2 ** levels names in all."""
    lines = ["a0: &a0 [x, x]"]
    lines += [f"a{n}: &a{n} [*a{n - 1}, *a{n - 1}]" for n in range(1, levels)]
    lines.append(f"reading_list:\n  name: bomb\n  tags: *a{levels - 1}")
    return "\n".join(lines) + "\n"


def test_yaml_aliases_are_refused() -> None:
    """About 600 bytes for 33 million names: refused before it is walked."""
    bomb = _doubling_aliases(25)
    assert len(bomb) < 700
    with _quickly(), pytest.raises(ReadingListFormatError, match="YAML aliases"):
        loads(bomb)


def test_yaml_aliases_are_refused_in_a_file(tmp_path: Path) -> None:
    path = tmp_path / "bomb.yaml"
    path.write_text(_doubling_aliases(25))
    with _quickly(), pytest.raises(ReadingListFormatError, match=r"\*a0 at line 2"):
        load(path)


def test_yaml_aliases_are_refused_in_a_download() -> None:
    bomb = _doubling_aliases(25).encode()
    with ReadingListSession() as session:
        session._transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, content=bomb)
        )
        with _quickly(), pytest.raises(ReadingListFormatError, match="YAML aliases"):
            session.fetch_url("https://lists.example/bomb.yaml")


def test_an_anchor_without_an_alias_is_read() -> None:
    result = loads("reading_list: &list\n  name: Anchored\n")
    assert result.reading_list["name"] == "Anchored"


def test_comicbox_never_writes_an_alias() -> None:
    """
    Ruamel aliases an object that appears twice; no list may come out so.

    The model copies dicts, but a date passes through as the same object,
    so one date for a cover and a store date is the real case.
    """
    day = date(2006, 7, 1)
    series = {"name": "Crimson Tide", "start_year": 2006}
    ids = {"metron": {"key": "1"}}
    reading_list = {
        "name": "Shared",
        "entries": [
            {
                "series": series,
                "issue": {"name": str(number)},
                "identifiers": ids,
                "date": {"cover_date": day, "store_date": day},
            }
            for number in (1, 2)
        ],
    }
    text = dumps(reading_list, ReadingListFormats.YAML)
    assert "&" not in text
    assert "*" not in text
    assert len(loads(text).reading_list["entries"]) == 2


# ---------------------------------------------------------------- nesting


@pytest.mark.parametrize(
    "text",
    [
        "reading_list:\n  name: " + "[" * 300 + "]" * 300,
        '{"reading_list": {"name": "x", "notes": '
        + "[" * 200_000
        + "]" * 200_000
        + "}}",
        "<ReadingList><Name>x</Name>" + "<a>" * 5000 + "</a>" * 5000 + "</ReadingList>",
    ],
    ids=["yaml", "json", "cbl"],
)
def test_nesting_too_deep_is_a_format_error(text: str) -> None:
    """
    Read, or refused in one line, but never a RecursionError.

    Which depends on the stack: ``make`` raises its soft limit to the hard
    one, 64 MiB here, and the C parsers then read what an 8 MiB stack
    cannot.
    """
    with _quickly(5):
        try:
            loads(text)
        except ReadingListFormatError as exc:
            message = str(exc)
        else:
            message = ""
    assert "\n" not in message


def test_detection_survives_nesting_too_deep() -> None:
    assert detect_format("[" * 200_000 + "]" * 200_000) in (
        None,
        ReadingListFormats.YAML,
    )


# --------------------------------------------------------------- warnings


def test_a_quoted_value_is_cut_short() -> None:
    long_name = "x" * 10_000
    result = loads(
        "reading_list:\n  name: Long\n  entries:\n"
        f"    - '{long_name}'\n"
        "    - series: {name: Ok}\n      issue: {name: '1'}\n"
    )
    (warning,) = result.warnings
    assert "is not an entry" in warning
    assert len(warning) < 120


# ------------------------------------------------- a root that is not a list

_TEXT_ROOTS = (
    '<?xml version="1.0"?><ReadingList>hello</ReadingList>',
    '<?xml version="1.0"?><ReadingList id="1">hello</ReadingList>',
)


@pytest.mark.parametrize("text", _TEXT_ROOTS, ids=["text", "attributes-and-text"])
@pytest.mark.parametrize("as_bytes", [False, True], ids=["str", "bytes"])
@pytest.mark.parametrize("fmt", [None, "cbl"], ids=["detected", "cbl"])
def test_a_reading_list_of_text_is_a_format_error(
    text: str, *, as_bytes: bool, fmt: str | None
) -> None:
    """``<ReadingList>hello</ReadingList>`` raised AttributeError."""
    data = text.encode() if as_bytes else text
    with pytest.raises(ReadingListFormatError):
        loads(data, fmt=fmt)
