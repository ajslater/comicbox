"""
comicbox.json pads page keys to the width of the highest page index.

The width was ceil(log10(max_page)), one digit short when the highest index
is a power of ten (11 or 101 pages), so those keys came out unpadded and in
lexicographic order. The width was also left over from an earlier dump on
the same schema instance when a book had no pages to pad.
"""

from __future__ import annotations

import json

import pytest

from comicbox.formats.comicbox.schema.json_schema import ComicboxJsonSchema


def _page_keys(schema: ComicboxJsonSchema, page_count: int) -> list[str]:
    pages = {index: {"size": 1} for index in range(page_count)}
    dumped = schema.dumps({"comicbox": {"pages": pages}})
    return list(json.loads(dumped)["comicbox"]["pages"])


@pytest.mark.parametrize("page_count", [2, 10, 11, 100, 101, 1000, 1001])
def test_page_keys_are_uniformly_padded_and_sorted(page_count: int) -> None:
    """Every key has the width of the highest index and the keys sort numerically."""
    keys = _page_keys(ComicboxJsonSchema(), page_count)
    width = len(str(page_count - 1))
    assert {len(key) for key in keys} == {width}
    assert keys == sorted(keys)
    assert int(keys[-1]) == page_count - 1


def test_small_dump_after_large_dump_is_not_padded() -> None:
    """A one page book is not padded to an earlier book's width."""
    schema = ComicboxJsonSchema()
    _page_keys(schema, 101)
    assert _page_keys(schema, 1) == ["0"]
