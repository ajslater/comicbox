"""
A malformed `-x` page range is a usage error, not a traceback.

`PageRangeAction` called `int()` unguarded, and argparse turns only its
own errors into a usage message, so `-x 1-3` (for `1:3`) crashed.
"""

from __future__ import annotations

import pytest

from comicbox.cli import get_args


@pytest.mark.parametrize(
    "value", ["1-3", "a:b", "x", "1:b", "", ":", "-1", "1_0", "1:2:3", " 1", "+2"]
)
def test_a_malformed_range_is_a_usage_error(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        get_args(["comicbox", "-x", value, "f.cbz"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert f"--extract-pages: expected N or N:M, got {value!r}" in err


@pytest.mark.parametrize("value", ["3:1", "5:4"])
def test_a_reversed_range_is_a_usage_error(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        get_args(["comicbox", "-x", value, "f.cbz"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert f"--extract-pages: {value!r} ends before it starts" in err


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", (0, 0)),
        ("1:3", (1, 3)),
        ("2", (2, 2)),
        ("2:2", (2, 2)),
        (":5", (None, 5)),
        (":2", (None, 2)),
        ("4:", (4, None)),
    ],
)
def test_a_valid_range_still_parses(
    value: str, expected: tuple[int | None, int | None]
) -> None:
    args = get_args(["comicbox", "-x", value, "f.cbz"])
    got = (
        getattr(args, "convert.extract_pages_from", None),
        getattr(args, "convert.extract_pages_to", None),
    )
    assert got == expected
