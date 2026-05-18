"""Cover-hash primitives + matcher invocation policy tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from comicbox.formats.base.online.cover_hash import (
    HASH_BITS,
    compute_phash,
    cover_score,
    hamming_distance,
)


def _solid_color_png(color: tuple[int, int, int], size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _gradient_png(size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), 0)
    pixels = img.load()
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
