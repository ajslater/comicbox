"""Unit tests for archive read primitives — namelist / infolist caching."""

from __future__ import annotations

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

    def spy_namelist(archive):  # type: ignore[no-untyped-def]
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
    cb._get_7zfactory()  # noqa: SLF001
    assert cb._namelist is not None  # noqa: SLF001
    assert cb._infolist is not None  # noqa: SLF001
    assert cb._7zfactory is not None  # noqa: SLF001

    cb.close()

    assert cb._archive is None  # noqa: SLF001
    assert cb._namelist is None  # noqa: SLF001
    assert cb._infolist is None  # noqa: SLF001
    assert cb._7zfactory is None  # noqa: SLF001


def test_context_manager_releases_cached_archive_state() -> None:
    """The `with` form calls close() and therefore drops cached state."""
    with Comicbox(CB7_SOURCE_PATH) as cb:
        cb.infolist()
        cb._get_7zfactory()  # noqa: SLF001
        held = cb

    assert held._archive is None  # noqa: SLF001
    assert held._infolist is None  # noqa: SLF001
    assert held._7zfactory is None  # noqa: SLF001


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
