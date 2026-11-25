"""
A tag write can be rolled back (B18, "tail rollback").

An in-place re-tag rewrites only the archive's tail. A write that fails puts
the old tail back, so the comic is as it was. Every archive here is generated
under tmp_path.
"""

from __future__ import annotations

import errno
import io
import os
import random
import shutil
import sys
import tarfile
import time
import zipfile
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.box.archive import rollback as rollback_module
from comicbox.box.archive import write as write_module
from comicbox.write import write_metadata
from tests.const import CIX_PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"
_TAGS: dict[str, Any] = {"series": {"name": "Crimson Tide"}, "issue": {"name": "1"}}


def _page(seed: int) -> bytes:
    # Seeded, so two copies of a comic are the same bytes: test data only.
    return random.Random(seed).randbytes(100_000)  # noqa: S311


def _pages(archive: zipfile.ZipFile) -> None:
    for index in range(3):
        archive.writestr(f"page-{index}.jpg", _page(index))


def _comic(tmp_path: Path, name: str = "comic.cbz") -> Path:
    """Three pages, then ComicInfo and MetronInfo, as comicbox writes them."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        _pages(archive)
    result = write_metadata(path, _TAGS, formats=[_CIX, _MI])
    assert result.written, result.error
    return path


def _tags(path: Path) -> dict[str, Any]:
    with Comicbox(path) as box:
        return dict(box.to_dict()["comicbox"])


def _retag(path: Path, summary: str = "New") -> Any:
    return write_metadata(path, {"summary": summary}, formats=[_CIX, _MI])


def _leftovers(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if p.name.startswith(".")}


def _fail_on_call(
    monkeypatch: pytest.MonkeyPatch,
    owner: Any,
    name: str,
    number: int,
    error: BaseException,
) -> None:
    """Make the ``number``th call of ``owner.name`` raise; let the others run."""
    real = getattr(owner, name)
    calls = {"n": 0}

    def fake(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == number:
            raise error
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, fake)


_DISK_FULL = OSError(errno.ENOSPC, "No space left on device")


# --------------------------------------------------------- in-memory rollback


def _fail_at_the_end_record(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    """Fail as zipfile starts the central directory, the new tags flushed."""
    real = vars(zipfile.ZipFile)["_write_end_record"]

    def end_record(self: zipfile.ZipFile) -> None:
        if self.mode == "a":
            assert self.fp is not None
            self.fp.flush()
            raise error
        real(self)

    monkeypatch.setattr(zipfile.ZipFile, "_write_end_record", end_record)


@pytest.mark.parametrize(
    ("step", "error"),
    [
        ("tail", _DISK_FULL),
        ("tail", KeyboardInterrupt()),
        ("end record", _DISK_FULL),
        ("end record", KeyboardInterrupt()),
    ],
    ids=["tail-full", "tail-interrupt", "end-record-full", "end-record-interrupt"],
)
def test_a_failure_at_each_step_leaves_the_comic_as_it_was(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: str, error: BaseException
) -> None:
    path = _comic(tmp_path)
    original = path.read_bytes()
    if step == "tail":
        # The second tag file: the first is already written into the tail.
        _fail_on_call(monkeypatch, zipfile.ZipFile, "writestr", 2, error)
    else:
        _fail_at_the_end_record(monkeypatch, error)

    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            _retag(path)
    else:
        result = _retag(path)
        assert not result.written
        assert result.error is not None
    monkeypatch.undo()

    assert path.read_bytes() == original
    assert {p.name for p in tmp_path.iterdir()} == {path.name}


def test_a_restore_that_fails_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _comic(tmp_path)
    _fail_on_call(monkeypatch, zipfile.ZipFile, "writestr", 2, _DISK_FULL)

    def restore(*_args: Any) -> None:
        raise OSError(errno.EIO, "the disk went away")

    monkeypatch.setattr(rollback_module, "_restore", restore)
    messages: list[str] = []
    handler = logger.add(messages.append, level="ERROR", format="{message}")
    try:
        assert not _retag(path).written
    finally:
        logger.remove(handler)

    assert any(str(path) in m and "may be damaged" in m for m in messages)


@contextmanager
def _read_only(directory: Path) -> Generator[None]:
    mode = directory.stat().st_mode
    directory.chmod(0o555)
    try:
        yield
    finally:
        directory.chmod(mode)


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions"
)
def test_a_read_only_directory_writes_with_the_in_memory_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "ro"
    directory.mkdir()
    path = _comic(directory)
    original = path.read_bytes()

    with _read_only(directory):
        assert _retag(path, "Works").written
        assert _tags(path)["summary"] == "Works"
        written = path.read_bytes()
        _fail_on_call(monkeypatch, zipfile.ZipFile, "writestr", 2, _DISK_FULL)
        assert not _retag(path, "Fails").written
        monkeypatch.undo()
        assert path.read_bytes() == written

    assert written != original
    assert _leftovers(directory) == set()


# ------------------------------------------------------------ the copy path


def _tags_first(tmp_path: Path) -> Path:
    """ComicInfo.xml stored before the pages, as some other tools write it."""
    path = tmp_path / "first.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "ComicInfo.xml", "<ComicInfo><Series>Crimson Tide</Series></ComicInfo>"
        )
        _pages(archive)
    return path


def test_a_tags_first_archive_is_copied_once_then_patched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _tags_first(tmp_path)
    copies: list[Path] = []
    real_copy = write_module.ComicboxArchiveWrite._patch_a_copy

    def spy(self: Any, target: Path, *args: Any) -> None:
        copies.append(target)
        real_copy(self, target, *args)

    monkeypatch.setattr(write_module.ComicboxArchiveWrite, "_patch_a_copy", spy)

    assert _retag(path, "Once").written
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert names[-2:] == ["ComicInfo.xml", "MetronInfo.xml"]
    first = path.read_bytes()
    assert _retag(path, "Twice").written

    assert copies == [path]
    with zipfile.ZipFile(path) as archive:
        tail = min(archive.getinfo(name).header_offset for name in names[-2:])
    assert path.read_bytes()[:tail] == first[:tail]
    assert _tags(path)["summary"] == "Twice"
    assert _leftovers(tmp_path) == set()


def test_a_failed_copy_leaves_the_comic_and_no_temporary_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _tags_first(tmp_path)
    original = path.read_bytes()
    _fail_on_call(monkeypatch, zipfile.ZipFile, "writestr", 2, _DISK_FULL)

    assert not _retag(path).written

    monkeypatch.undo()
    assert path.read_bytes() == original
    assert _leftovers(tmp_path) == set()


def test_a_leftover_temporary_archive_is_removed_by_the_next_write(
    tmp_path: Path,
) -> None:
    path = _tags_first(tmp_path)
    leftover = write_module.tmp_archive_path(path)
    leftover.write_bytes(b"a killed conversion's")

    assert _retag(path).written

    assert not leftover.exists()


# ------------------------------------------------------------------ names


def _watch_names(
    monkeypatch: pytest.MonkeyPatch, directory: Path
) -> Callable[[], list[set[str]]]:
    """Record every name in a directory at each step of a write."""
    seen: list[set[str]] = []

    def watching(owner: Any, name: str) -> None:
        real = getattr(owner, name)

        def fake(*args: Any, **kwargs: Any) -> Any:
            seen.append({p.name for p in directory.iterdir()})
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, fake)

    watching(zipfile.ZipFile, "writestr")
    watching(write_module.ComicboxArchiveWrite, "_cleanup_tmp_archive")
    return lambda: seen


@pytest.mark.parametrize("archive", ["tail", "tags first", "cbt"])
def test_nothing_but_a_copys_temporary_archive_appears_during_a_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, archive: str
) -> None:
    """No file with a comic suffix, and nothing at all beside a tail write."""
    if archive == "tail":
        path = _comic(tmp_path)
    elif archive == "tags first":
        path = _tags_first(tmp_path)
    else:
        # A tar, converted to a CBZ beside it.
        path = tmp_path / "comic.cbt"
        page = _page(0)
        info = tarfile.TarInfo("page-0.jpg")
        info.size = len(page)
        with tarfile.open(path, "w") as tar:
            tar.addfile(info, io.BytesIO(page))
    allowed = {path.name}
    if archive != "tail":
        allowed.add(write_module.tmp_archive_path(path).name)
    seen = _watch_names(monkeypatch, tmp_path)

    assert _retag(path).written

    monkeypatch.undo()
    assert seen()
    assert all(names <= allowed for names in seen())
    assert all(path.name in names for names in seen())


# --------------------------------------------------------------------- PDF


def test_a_failed_pdf_write_leaves_the_pdf_as_it_was(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pdffile saves a changed document on close, even after an error."""
    from pdffile import PDFFile

    path = tmp_path / "comic.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    original = path.read_bytes()
    _fail_on_call(monkeypatch, PDFFile, "writestr", 1, _DISK_FULL)

    result = write_metadata(path, {"summary": "New"}, formats=[_CIX])

    assert not result.written
    monkeypatch.undo()
    assert path.read_bytes() == original
    assert {p.name for p in tmp_path.iterdir()} == {"comic.pdf"}


# ------------------------------------------------------------- same output


@pytest.mark.parametrize(
    ("formats", "patch"),
    [
        ([_CIX], {"summary": "New"}),
        ([_CIX, _MI], {"summary": "New"}),
        (["COMIC_BOOK_INFO"], {"summary": "A comment"}),
        (["keep"], {"summary": "Kept"}),
    ],
    ids=["cix", "cix+mi", "comment", "keep"],
)
def test_the_rollback_changes_no_byte_of_a_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    formats: list[str],
    patch: dict[str, Any],
) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    kept = _comic(tmp_path / "kept")
    plain = _comic(tmp_path / "plain")
    assert kept.read_bytes() == plain.read_bytes()

    assert write_metadata(kept, patch, formats=formats).written

    @contextmanager
    def no_rollback(*_args: Any) -> Generator[None]:
        yield

    monkeypatch.setattr(write_module, "TailRollback", no_rollback)
    assert write_metadata(plain, patch, formats=formats).written

    assert kept.read_bytes() == plain.read_bytes()
