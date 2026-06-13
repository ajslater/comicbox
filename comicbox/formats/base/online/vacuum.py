"""
Conditional SQLite VACUUM for the online caches.

mokkari and simyan both delete expired rows when their cache opens, but
neither ever VACUUMs — a DELETE only moves pages onto the free list, it
doesn't return them to the OS, so the file keeps its high-water-mark size.
This reclaims that space, but only when there's enough of it to justify
rewriting the whole file.

The trigger is the free-page ratio, not the calendar or the raw file size:
VACUUM exists to reclaim free pages, so we vacuum exactly when there are
enough of them. It's self-limiting — a freshly vacuumed db has ~0 free
pages, so it won't re-trigger until expiry deletes accumulate again — and
needs no persisted "last vacuumed" state.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

# Default page size is 4096 bytes, so 256 pages ~= 1 MiB. Below this the
# file is small enough that reclaiming free pages isn't worth a full rewrite.
_MIN_PAGES = 256

# VACUUM only when at least this fraction of the file is free pages left
# behind by expiry deletes.
_FREELIST_RATIO = 0.25


def vacuum_if_bloated(db_path: Path | str) -> bool:
    """
    VACUUM a sqlite cache only when reclaimable space is worth it.

    Returns True if a VACUUM ran. A cheap no-op (one PRAGMA pair, or less)
    for missing, small, or already-compact files. Best-effort housekeeping:
    a locked/busy db is skipped rather than allowed to fail a lookup.
    """
    path = Path(db_path)
    if not path.exists():
        return False
    try:
        # autocommit (isolation_level=None): VACUUM cannot run inside a
        # transaction, which the sqlite3 module would otherwise open.
        with closing(sqlite3.connect(path, isolation_level=None)) as conn:
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            if page_count < _MIN_PAGES:
                return False
            freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
            if freelist < page_count * _FREELIST_RATIO:
                return False
            conn.execute("VACUUM")
    except sqlite3.OperationalError:
        # Another connection holds the write lock, or the db is busy.
        return False
    return True
