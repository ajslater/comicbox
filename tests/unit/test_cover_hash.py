"""Cover-hash primitives + matcher invocation policy tests."""

from __future__ import annotations

import sqlite3
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from comicbox.formats.base.online.cover_hash import (
    HASH_BITS,
    CoverHashUrlCache,
    compute_phash,
    cover_score,
    hamming_distance,
)

if TYPE_CHECKING:
    from pathlib import Path


def _solid_color_png(color: tuple[int, int, int], size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _gradient_png(size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), 0)
    pixels = img.load()
    assert pixels is not None
    for x in range(size):
        for y in range(size):
            pixels[x, y] = (x * 4 % 256, y * 4 % 256, (x + y) * 2 % 256)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_compute_phash_returns_hex_string() -> None:
    h = compute_phash(_solid_color_png((255, 0, 0)))
    assert isinstance(h, str)
    assert len(h) == HASH_BITS // 4  # hex digits = bits/4


def test_phash_stable_for_same_image() -> None:
    img = _gradient_png()
    assert compute_phash(img) == compute_phash(img)


def test_hamming_distance_identical_is_zero() -> None:
    h = compute_phash(_gradient_png())
    assert hamming_distance(h, h) == 0


def test_hamming_distance_very_different() -> None:
    a = compute_phash(_solid_color_png((255, 0, 0)))
    # Use a gradient — meaningfully different from the solid color.
    b = compute_phash(_gradient_png())
    # We only care that they're meaningfully different.
    assert hamming_distance(a, b) > 0


def test_cover_score_identical_is_one() -> None:
    h = compute_phash(_gradient_png())
    assert cover_score(h, h) == pytest.approx(1.0)


def test_cover_score_clamped_to_unit_interval() -> None:
    h1 = compute_phash(_solid_color_png((255, 0, 0)))
    h2 = compute_phash(_gradient_png())
    s = cover_score(h1, h2)
    assert 0.0 <= s <= 1.0


# ----------------------------------------------- CoverHashUrlCache


def test_cover_hash_url_cache_round_trip(tmp_path: Path) -> None:
    cache = CoverHashUrlCache(tmp_path / "cover_hashes.sqlite")
    assert cache.get("http://example.com/x.jpg") is None
    cache.set("http://example.com/x.jpg", "abcdef0123456789")
    assert cache.get("http://example.com/x.jpg") == "abcdef0123456789"


def test_cover_hash_url_cache_overwrites(tmp_path: Path) -> None:
    cache = CoverHashUrlCache(tmp_path / "cover_hashes.sqlite")
    cache.set("u", "h1")
    cache.set("u", "h2")
    assert cache.get("u") == "h2"


def test_cover_hash_url_cache_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "cover_hashes.sqlite"
    CoverHashUrlCache(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = [r[0] for r in rows]
    assert "cover_hashes" in table_names
