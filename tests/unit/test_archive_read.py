"""Unit tests for archive read primitives — namelist / infolist caching."""

from __future__ import annotations

import shutil
import subprocess
import sys
from sys import maxsize

from py7zr import SevenZipFile
from py7zr.io import BytesIOFactory

from comicbox.box import Comicbox
from comicbox.box.archive import archive as archive_module
from comicbox.config import get_config
from tests.const import CB7_SOURCE_PATH, CIX_CBZ_SOURCE_PATH, TEST_FILES_DIR

RESOURCE_FORK_ARCHIVE = TEST_FILES_DIR / "macos_resource_fork.cbz"


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


def test_readfile_ignores_a_same_named_directory_in_the_cwd(tmp_path, monkeypatch):
    """
    A member name is the archive's, not the filesystem's.

    The dir guard called Path(filename).is_dir(), which resolves a relative
    archive name against the process cwd — so a directory that happened to
    share a page's name made the read return b"" and the page vanished.
    """
    import zipfile

    cbz = tmp_path / "trap.cbz"
    page = "CaptainScience#1_01.jpg"
    payload = b"\xff\xd8\xff\xe0page-data"
    with zipfile.ZipFile(cbz, "w") as zf:
        zf.writestr(page, payload)

    # cwd now holds a *directory* named exactly like the archive's page.
    cwd = tmp_path / "cwd"
    (cwd / page).mkdir(parents=True)
    monkeypatch.chdir(cwd)

    with Comicbox(cbz) as cb:
        assert cb._archive_readfile(page) == payload


def test_readfile_still_skips_a_real_archive_directory_entry():
    """The guard's actual job: a directory member of the archive reads empty."""
    with Comicbox(RESOURCE_FORK_ARCHIVE) as cb:
        dirnames = cb.dirnames()
        assert "__MACOSX/" in dirnames
        assert cb._archive_readfile("__MACOSX/") == b""
        # Only the directory entry is skipped; real members still read.
        assert cb._archive_readfile("CaptainScience#1_01.jpg")


def _spy_on_7z_extract(monkeypatch) -> list[list[str]]:
    """Record the target list of every py7zr extract call."""
    batches: list[list[str]] = []
    real_extract = SevenZipFile.extract

    def spy_extract(self, path=None, targets=None, *args, **kwargs):
        batches.append(list(targets) if targets is not None else [])
        return real_extract(self, path, targets, *args, **kwargs)

    monkeypatch.setattr(SevenZipFile, "extract", spy_extract)
    return batches


def test_cb7_conversion_batches_the_extract(tmp_path, monkeypatch) -> None:
    """
    Converting a CB7 pulls its members out in batches, not one at a time.

    A solid 7z folder is decompressed from its start on every extract
    call, so a page-at-a-time copy costs one full pass per page and makes
    conversion quadratic in page count.
    """
    cb7 = tmp_path / "batched.cb7"
    shutil.copy(CB7_SOURCE_PATH, cb7)
    batches = _spy_on_7z_extract(monkeypatch)

    config = get_config({"comicbox": {"convert": {"cbz": True}}})
    with Comicbox(cb7, config=config) as cb:
        pagenames = cb.get_page_filenames()
        cb.dump()

    copy_batches = [b for b in batches if len(b) > 1]
    assert len(copy_batches) == 1, "the page copy did not batch into one pass"
    assert set(copy_batches[0]) >= set(pagenames), "the batch did not cover every page"


def test_cb7_batch_respects_the_resident_byte_cap(tmp_path, monkeypatch) -> None:
    """A cap smaller than the archive splits the copy into several passes."""
    from comicbox.box.archive import read as read_module

    cb7 = tmp_path / "capped.cb7"
    shutil.copy(CB7_SOURCE_PATH, cb7)
    # Two of this fixture's ~4 KiB pages per batch.
    monkeypatch.setattr(read_module, "_7Z_BATCH_MAX_BYTES", 9000)
    batches = _spy_on_7z_extract(monkeypatch)

    config = get_config({"comicbox": {"convert": {"cbz": True}}})
    with Comicbox(cb7, config=config) as cb:
        cb.dump()

    copy_batches = [b for b in batches if len(b) > 1]
    assert copy_batches, "the page copy never batched its extract"
    assert max(len(b) for b in copy_batches) <= 3, (
        "the byte cap did not bound the batch size"
    )
    assert len(copy_batches) > 1, "a capped copy should need several passes"


def test_cb7_batch_conversion_copies_every_page_intact(tmp_path) -> None:
    """Batching must not change a single output byte."""
    import zipfile

    cb7 = tmp_path / "intact.cb7"
    shutil.copy(CB7_SOURCE_PATH, cb7)

    factory = BytesIOFactory(maxsize)
    with SevenZipFile(CB7_SOURCE_PATH) as z:
        z.extractall(factory=factory)
        source_pages = {
            name: buf.read()
            for name, buf in factory.products.items()
            if name.lower().endswith(".jpg")
        }
    assert source_pages

    config = get_config({"comicbox": {"convert": {"cbz": True}}})
    with Comicbox(cb7, config=config) as cb:
        cb.dump()

    with zipfile.ZipFile(cb7.with_suffix(".cbz")) as zf:
        written = {n: zf.read(n) for n in zf.namelist() if n.lower().endswith(".jpg")}
    assert written == source_pages


def test_7z_read_releases_each_page_buffer() -> None:
    """
    The factory must not retain a buffer for every page ever read.

    py7zr's BytesIOFactory keeps every member it decompresses, so a
    whole-archive read used to hold all of its pages resident until the
    box was closed.
    """
    with Comicbox(CB7_SOURCE_PATH) as cb:
        pagenames = cb.get_page_filenames()
        assert len(pagenames) > 1
        for pagename in pagenames:
            assert cb.get_page_by_filename(pagename)
            factory = cb._get_7zfactory()
            assert factory is not None
            assert not factory.products, (
                f"{pagename}'s buffer was retained after the read"
            )


def test_7z_repeat_read_returns_the_same_bytes() -> None:
    """Popping the buffer must not make a second read of a page come back empty."""
    with Comicbox(CB7_SOURCE_PATH) as cb:
        pagename = cb.get_page_filenames()[0]
        first = cb.get_page_by_filename(pagename)
        assert first
        assert cb.get_page_by_filename(pagename) == first
