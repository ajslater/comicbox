"""Tests for the conditional SQLite VACUUM helper."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from comicbox.formats.base.online.vacuum import vacuum_if_bloated

if TYPE_CHECKING:
    from pathlib import Path


def _freelist(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("PRAGMA freelist_count").fetchone()[0]


def _make_bloated_db(db_path: Path, rows: int = 12000) -> None:
    """Create a db big enough to clear the page floor, then free ~all of it."""
    with sqlite3.connect(db_path, isolation_level=None) as conn:
        conn.execute("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany(
            "INSERT INTO t(k, v) VALUES (?, ?)",
            [(i, "x" * 400) for i in range(rows)],
        )
        # Delete almost everything: pages move to the free list but the file
        # keeps its size until a VACUUM.
        conn.execute("DELETE FROM t WHERE k > 0")


def test_missing_file_is_noop(tmp_path: Path) -> None:
    assert vacuum_if_bloated(tmp_path / "absent.sqlite") is False


def test_small_file_skipped(tmp_path: Path) -> None:
    db_path = tmp_path / "small.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE t (k INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO t(k) VALUES (1)")
        conn.execute("DELETE FROM t")
    # Under the 256-page floor, so no rewrite regardless of free pages.
    assert vacuum_if_bloated(db_path) is False


def test_bloated_file_vacuumed(tmp_path: Path) -> None:
    db_path = tmp_path / "bloated.sqlite"
    _make_bloated_db(db_path)
    assert _freelist(db_path) > 0
    size_before = db_path.stat().st_size

    assert vacuum_if_bloated(db_path) is True

    assert _freelist(db_path) == 0
    assert db_path.stat().st_size < size_before


def test_compact_file_skipped(tmp_path: Path) -> None:
    """A large but already-compact db has no free pages to reclaim."""
    db_path = tmp_path / "compact.sqlite"
    _make_bloated_db(db_path)
    vacuum_if_bloated(db_path)  # compacts it
    assert _freelist(db_path) == 0
    # Second pass: nothing left to reclaim.
    assert vacuum_if_bloated(db_path) is False
