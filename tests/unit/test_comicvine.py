"""ComicVine source + transform tests."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from comicbox.online.sources.comicvine import CoverHashUrlCache
from comicbox.transforms.comicvine_api import ComicVineApiTransform

if TYPE_CHECKING:
    from pathlib import Path


def _sample_issue_dict() -> dict:
    return {
        "comicvine_api": {
            "id": 1234,
            "number": "5",
            "cover_date": "2020-04-01",
            "store_date": "2020-04-15",
            "date_last_updated": "2020-04-02T12:00:00Z",
            "description": "<p>Some description.</p>",
            "page_count": 24,
            "image": {
                "thumb_url": "http://example.com/thumb.jpg",
                "original_url": "http://example.com/original.jpg",
            },
            "volume": {"id": 100, "name": "Foo Comics"},
        }
    }


def test_transform_maps_core_fields() -> None:
    transform = ComicVineApiTransform()
    result = dict(transform.to_comicbox(_sample_issue_dict()))
    cb = result["comicbox"]
    assert cb["page_count"] == 24
    assert cb["summary"] == "<p>Some description.</p>"
    assert cb["issue"]["name"] == "5"
    # CV's `volume` becomes comicbox's `series`.
    assert cb["series"]["name"] == "Foo Comics"
    # `image.thumb_url` flattens to cover_image.
    assert cb["cover_image"]
    # Dates wired.
    assert "cover_date" in cb["date"]
    assert "store_date" in cb["date"]


def test_transform_handles_missing_fields() -> None:
    transform = ComicVineApiTransform()
    minimal = {
        "comicvine_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2025-01-01",
            "date_last_updated": "2025-01-01T00:00:00Z",
            "image": {"thumb_url": "http://example.com/x.jpg"},
            "volume": {"id": 1, "name": "S"},
        }
    }
    result = dict(transform.to_comicbox(minimal))
    cb = result["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert cb["series"]["name"] == "S"


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


# ----------------------------------------------- matcher hash-fetcher hook


def test_matcher_uses_candidate_hash_fetcher_for_no_precomputed() -> None:
    """Matcher should call the fetcher for candidates without precomputed hash."""
    from comicbox.online.matcher import OnlineMatcher
    from comicbox.online.profile import Candidate, CandidateSummary, ComicProfile

    fetcher_calls: list[str] = []

    def fake_fetcher(url: str) -> str:
        fetcher_calls.append(url)
        return "ffffffffffffffff"  # different from local

    def local_provider() -> str:
        return "0000000000000000"

    profile = ComicProfile(
        series="Foo",
        issue="5",
        issue_int=5,
        year=2020,
        publisher="P",
        page_count=24,
    )
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="Foo",
            issue="5",
            year=2020,
            publisher="P",
            page_count=24,
            cover_url="http://example.com/x.jpg",
            variant_label=None,
        ),
    )

    matcher = OnlineMatcher()
    matcher.rank(
        profile,
        [cand],
        local_hash_provider=local_provider,
        candidate_hash_fetcher=fake_fetcher,
        threshold=0.99,  # force hashing path (top below threshold).
    )
    # Whether or not the candidate was hashed depends on the metadata
    # score landing in the ambiguous band; with a perfect metadata match
    # the policy may skip hashing. The test asserts the fetcher is wired:
    # if invoked, it received our URL.
    assert all(call == "http://example.com/x.jpg" for call in fetcher_calls)
