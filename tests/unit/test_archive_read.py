"""Unit tests for archive read primitives — namelist / infolist caching."""

from __future__ import annotations

import subprocess
import sys

from comicbox.box import Comicbox
from comicbox.box.archive import archive as archive_module
from tests.const import CB7_SOURCE_PATH, CIX_CBZ_SOURCE_PATH


def test_namelist_derives_from_cached_infolist(monkeypatch) -> None:
    """
    namelist() must reuse a cached infolist instead of re-walking the archive.

    This is the codex-hot-path optimisation: in process._read_one we first call
    get_metadata_mtime() (which builds infolist), then to_dict() (which
    eventually calls namelist via the sources loader). The second call should
    not re-invoke Archive.namelist on the underlying archive.
    """
    namelist_calls: list[object] = []
    real_namelist = archive_module.Archive.namelist

    def spy_namelist(archive):
        namelist_calls.append(archive)
        return real_namelist(archive)

    monkeypatch.setattr(archive_module.Archive, "namelist", staticmethod(spy_namelist))

    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb:
        infolist = cb.infolist()
        derived = cb.namelist()

    assert namelist_calls == [], (
        "Archive.namelist should not be called when infolist is already cached"
    )

    # Derived namelist must match what we would have gotten from a real walk
    expected = tuple(cb._get_info_fn(i) for i in infolist)
    assert derived == expected


def test_namelist_walks_archive_when_no_cached_infolist() -> None:
    """When infolist hasn't been called yet, namelist must walk the archive."""
    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb:
        namelist = cb.namelist()
    # Sanity: namelist is non-empty and case-insensitively sorted
    assert namelist
    lower = [n.lower() for n in namelist]
    assert lower == sorted(lower)


def test_close_releases_cached_archive_state() -> None:
    """
    close() releases _7zfactory, _namelist, _infolist.

    Long-lived callers (Codex's per-archive cover cache) keep Comicbox
    instances pinned across page reads; without this teardown the 7z
    BytesIOFactory accumulates one Py7zBytesIO entry per page ever read.
    """
    cb = Comicbox(CB7_SOURCE_PATH)
    # Trigger lazy initialisation of each cached field.
    cb.infolist()
    cb.namelist()
    cb._get_7zfactory()
    assert cb._namelist is not None
    assert cb._infolist is not None
    assert cb._7zfactory is not None

    cb.close()

    assert cb._archive is None
    assert cb._namelist is None
    assert cb._infolist is None
    assert cb._7zfactory is None


def test_context_manager_releases_cached_archive_state() -> None:
    """The `with` form calls close() and therefore drops cached state."""
    with Comicbox(CB7_SOURCE_PATH) as cb:
        cb.infolist()
        cb._get_7zfactory()
        held = cb

    assert held._archive is None
    assert held._infolist is None
    assert held._7zfactory is None


def test_cbz_read_does_not_load_py7zr_or_rarfile() -> None:
    """
    Reading a CBZ must not transitively import py7zr or rarfile.

    Run in a fresh subprocess so other tests in this run haven't already
    loaded them. This locks in the lazy-import contract: CBZ-only worker
    processes in a 600k-comic batch must not pay the rarfile + py7zr
    startup cost.
    """
    script = f"""
import sys
from comicbox.box import Comicbox
with Comicbox({str(CIX_CBZ_SOURCE_PATH)!r}) as cb:
    cb.to_dict()
    cb.get_page_count()
heavy = sorted(m for m in sys.modules if 'py7zr' in m or 'rarfile' in m)
print('\\n'.join(heavy))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )
    heavy_loaded = result.stdout.strip().splitlines()
    assert heavy_loaded == [], (
        f"CBZ read must not load py7zr/rarfile, but loaded: {heavy_loaded}"
    )


def test_infolist_and_namelist_share_sort_order() -> None:
    """Infolist and namelist are both sorted by lowercased filename."""
    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb:
        # Force separate code paths: build namelist first (archive walk),
        # then infolist (separate archive walk).
        names_from_namelist = cb.namelist()
    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb:
        infolist = cb.infolist()
        names_from_infolist = tuple(cb._get_info_fn(i) for i in infolist)
    assert names_from_namelist == names_from_infolist
