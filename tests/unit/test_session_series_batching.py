"""Session-level tests for series-first batching orchestration."""

from __future__ import annotations

from pathlib import Path

from comicbox.online_session import (
    OnlineCredentials,
    OnlineSession,
    _filename_series_fingerprint,
)

VALID = OnlineCredentials(metron_user="u", metron_password="p")


# --- filename fingerprint ---------------------------------------------------


def test_filename_fingerprint_groups_same_series() -> None:
    """Two issues of the same series share a filename fingerprint."""
    a = Path("Spider-Man #001 (2018).cbz")
    b = Path("Spider-Man #002 (2018).cbz")
    assert _filename_series_fingerprint(a) == _filename_series_fingerprint(b)


def test_filename_fingerprint_separates_series() -> None:
    a = Path("Spider-Man #001 (2018).cbz")
    b = Path("Batman #001 (2018).cbz")
    assert _filename_series_fingerprint(a) != _filename_series_fingerprint(b)


def test_filename_fingerprint_falls_back_on_unparseable() -> None:
    """When comicfn2dict yields no series, fingerprint prefixes with ~."""
    # Issue-only filenames yield no series under comicfn2dict.
    fp = _filename_series_fingerprint(Path("#42 (2020).cbz"))
    assert fp.startswith("~")


# --- session-level wiring ---------------------------------------------------


def test_series_cache_snapshot_starts_empty() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID)
    assert session.series_cache_snapshot() == {}


def test_preload_series_resolution_seeds_cache() -> None:
    """Codex's persistence path: replay prior resolutions before a run."""
    session = OnlineSession(sources={"metron"}, credentials=VALID)
    session.preload_series_resolution(
        source="metron", series_fingerprint="foo|2018|", volume_id=42
    )
    snap = session.series_cache_snapshot()
    assert snap[("metron", "foo|2018|")] == 42


def test_preload_is_first_writer_wins() -> None:
    """Preload after seed → no-op; cache value unchanged."""
    session = OnlineSession(sources={"metron"}, credentials=VALID)
    session.preload_series_resolution(
        source="metron", series_fingerprint="foo", volume_id=1
    )
    session.preload_series_resolution(
        source="metron", series_fingerprint="foo", volume_id=2
    )
    assert session.series_cache_snapshot()[("metron", "foo")] == 1


def test_clear_series_cache_empties_dict() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID)
    session.preload_series_resolution(
        source="metron", series_fingerprint="foo", volume_id=1
    )
    session.clear_series_cache()
    assert session.series_cache_snapshot() == {}


def test_series_batching_can_be_disabled() -> None:
    """series_batching=False suppresses both the cache wiring and the sort."""
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, series_batching=False
    )
    # The cache still exists (so preload_series_resolution still works),
    # but _run_one won't pass it to Comicbox. tag_many won't sort either.
    paths = [
        Path("Spider-Man #002 (2018).cbz"),
        Path("Spider-Man #001 (2018).cbz"),
        Path("Batman #001 (2018).cbz"),
    ]
    # Cancel before running so we don't actually try to tag files;
    # the assertion is just about ordering of the produced results.
    session.cancel()
    out = [r.path for r in session.tag_many(paths)]
    # series_batching=False → preserved input order.
    assert out == paths


def test_series_batching_sorts_by_fingerprint() -> None:
    """With series_batching=True, paths cluster by filename fingerprint."""
    session = OnlineSession(sources={"metron"}, credentials=VALID)
    paths = [
        Path("Spider-Man #002 (2018).cbz"),
        Path("Batman #001 (2018).cbz"),
        Path("Spider-Man #001 (2018).cbz"),
    ]
    session.cancel()
    out = [r.path for r in session.tag_many(paths)]
    # Spider-Man comics adjacent; Batman not interleaved.
    sp_indices = [i for i, p in enumerate(out) if "Spider" in p.name]
    bm_indices = [i for i, p in enumerate(out) if "Batman" in p.name]
    assert max(sp_indices) - min(sp_indices) == len(sp_indices) - 1
    assert max(bm_indices) - min(bm_indices) == len(bm_indices) - 1
