"""
The library's two page-range calls read the same pages for the same range.

`get_pages` reads an end of None, or below 0, as the last page (batch 6).
`extract_pages` read an end of -1 as an empty slice and extracted nothing.
A start below 0 counts from the last page in both, as a Python slice does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

# The test comic has five pages.
_RANGES = [
    ((0, None), 5),
    ((0, -1), 5),
    ((0, -2), 5),
    ((3, -1), 2),
    ((-1, None), 1),
    ((-2, -1), 2),
    ((1, 2), 2),
]


@pytest.mark.parametrize(("page_range", "count"), _RANGES)
def test_extract_pages_and_get_pages_agree(
    tmp_path: Path, page_range: tuple[int, int | None], count: int
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb:
        read = list(cb.get_pages(*page_range))
        cb.extract_pages(*page_range, out)
    extracted = sorted(path.read_bytes() for path in out.iterdir())
    assert len(read) == count
    assert extracted == sorted(read)
