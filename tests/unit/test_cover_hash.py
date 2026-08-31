"""Cover-hash primitives + matcher invocation policy tests."""

from __future__ import annotations

import sqlite3
import threading
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from typing_extensions import override

from comicbox.formats.base.online.cover_hash import (
    HASH_BITS,
    CoverFetchPool,
    CoverHashUrlCache,
    compute_phash,
    cover_score,
    hamming_distance,
)

if TYPE_CHECKING:
    from collections.abc import Callable
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


# ------------------------------------------------ batch cache + fetch pool


def test_cover_hash_url_cache_get_many_round_trip(tmp_path: Path) -> None:
    """One query answers a whole top-K instead of one connection per URL."""
    cache = CoverHashUrlCache(tmp_path / "c.sqlite")
    cache.set_many([("http://a", "aaaa"), ("http://b", "bbbb")])
    assert cache.get_many(["http://a", "http://b", "http://missing"]) == {
        "http://a": "aaaa",
        "http://b": "bbbb",
    }
    cache.close()


def test_cover_hash_url_cache_reuses_one_connection(tmp_path: Path) -> None:
    """The connection is held for the cache's lifetime, not per call."""
    cache = CoverHashUrlCache(tmp_path / "c.sqlite")
    first = cache._conn
    cache.set("http://a", "aaaa")
    cache.get("http://a")
    assert cache._conn is first
    cache.close()


def test_cover_hash_url_cache_set_many_ignores_blanks(tmp_path: Path) -> None:
    """Empty URLs and empty hashes are never stored."""
    cache = CoverHashUrlCache(tmp_path / "c.sqlite")
    cache.set_many([("", "aaaa"), ("http://a", ""), ("http://b", "bbbb")])
    assert cache.get_many(["", "http://a", "http://b"]) == {"http://b": "bbbb"}
    cache.close()


def test_cover_hash_url_cache_get_many_chunks_large_input(tmp_path: Path) -> None:
    """More URLs than SQLite's variable limit still resolve in full."""
    cache = CoverHashUrlCache(tmp_path / "c.sqlite")
    pairs = [(f"http://u{i}", f"h{i}") for i in range(cache._MAX_VARS * 2 + 7)]
    cache.set_many(pairs)
    assert cache.get_many([u for u, _ in pairs]) == dict(pairs)
    cache.close()


def test_cover_hash_url_cache_close_is_idempotent(tmp_path: Path) -> None:
    """Closing twice is safe — the box closes it, and so may a caller."""
    cache = CoverHashUrlCache(tmp_path / "c.sqlite")
    cache.close()
    cache.close()


class _StubPool(CoverFetchPool):
    """A pool whose single-cover fetch is stubbed; no network, no PIL."""

    def __init__(self, stub: Callable[[str], str | None], max_workers: int = 8) -> None:
        super().__init__(max_workers=max_workers)
        self._stub = stub
        self.seen: list[str] = []

    @override
    def fetch_hash(self, url: str) -> str | None:
        self.seen.append(url)
        return self._stub(url)


def test_cover_fetch_pool_fetches_concurrently() -> None:
    """
    The pool overlaps downloads instead of serializing them.

    These GETs hit the sources' image CDNs, not their rate-limited API
    hosts, so serializing them was pure wall-clock loss: the matcher
    hashes up to 15 candidates for one ambiguous comic.
    """
    barrier = threading.Barrier(3, timeout=5)

    def stub(url: str) -> str:
        # Blocks until all three are in flight; a serial pool never gets
        # here and the barrier times out.
        barrier.wait()
        return f"hash-{url[-1]}"

    pool = _StubPool(stub, max_workers=3)
    assert pool.fetch_hashes(["http://a", "http://b", "http://c"]) == {
        "http://a": "hash-a",
        "http://b": "hash-b",
        "http://c": "hash-c",
    }
    pool.close()


def test_cover_fetch_pool_drops_failures() -> None:
    """A cover that won't hash is a missing signal, never a failed lookup."""
    pool = _StubPool(lambda url: None if url.endswith("b") else "ok", max_workers=2)
    assert pool.fetch_hashes(["http://a", "http://b"]) == {"http://a": "ok"}
    pool.close()


def test_cover_fetch_pool_dedupes_urls() -> None:
    """Two candidates sharing a cover URL cost one download."""
    pool = _StubPool(lambda _url: "h", max_workers=4)
    pool.fetch_hashes(["http://a", "http://a", "http://a"])
    assert pool.seen == ["http://a"]
    pool.close()


def test_cover_fetch_pool_empty_input_does_no_work() -> None:
    """No URLs means no client, no threads."""
    pool = CoverFetchPool()
    assert pool.fetch_hashes([]) == {}
    assert pool._client is None


def test_cover_fetch_pool_close_is_idempotent() -> None:
    """Closing an unused pool, or one already closed, is safe."""
    pool = CoverFetchPool()
    pool.close()
    pool.close()
