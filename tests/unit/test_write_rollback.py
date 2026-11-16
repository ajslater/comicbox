"""
A tag write can be rolled back (B18, "tail rollback").

An in-place re-tag rewrites only the archive's tail. A write that fails puts
the old tail back; one killed part way leaves a journal that the next open
replays. Every archive here is generated under tmp_path.
"""

from __future__ import annotations

import errno
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.archive import journal as journal_module
from comicbox.box.archive import write as write_module
from comicbox.box.archive.journal import TailJournal, journal_path
from comicbox.exceptions import DestinationOccupiedError
from comicbox.write import write_metadata
from tests.const import CIX_PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"
_TAGS: dict[str, Any] = {"series": {"name": "Civil War"}, "issue": {"name": "1"}}
_COMIC_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".cb7", ".pdf"})


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


def _comic_files(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if p.suffix.lower() in _COMIC_SUFFIXES}


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


@pytest.mark.parametrize(
    ("step", "error"),
    [
        ("journal", KeyboardInterrupt()),
        ("tail", _DISK_FULL),
        ("tail", KeyboardInterrupt()),
        ("flush", _DISK_FULL),
        ("delete", PermissionError(errno.EACCES, "Permission denied")),
    ],
    ids=["journal-interrupt", "tail-full", "tail-interrupt", "flush", "delete"],
)
def test_a_failure_at_each_step_leaves_the_comic_as_it_was(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: str, error: BaseException
) -> None:
    path = _comic(tmp_path)
    original = path.read_bytes()
    if step == "journal":
        # The journal's own flush.
        _fail_on_call(monkeypatch, journal_module, "_flush", 1, error)
    elif step == "tail":
        # The second tag file: the first is already written into the tail.
        _fail_on_call(monkeypatch, zipfile.ZipFile, "writestr", 2, error)
    elif step == "flush":
        # The journal's fsync, then the archive's.
        _fail_on_call(monkeypatch, journal_module.os, "fsync", 2, error)
    else:
        _fail_on_call(monkeypatch, type(path), "unlink", 1, error)

    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            _retag(path)
    else:
        result = _retag(path)
        assert not result.written
        assert result.error is not None
    monkeypatch.undo()

    assert path.read_bytes() == original
    assert _leftovers(tmp_path) == set()


def test_a_journal_the_disk_cannot_hold_is_done_without(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A full disk at the journal: the write goes ahead, and leaves no part of it."""
    path = _comic(tmp_path)
    _fail_on_call(monkeypatch, journal_module, "_flush", 1, _DISK_FULL)

    result = _retag(path)

    assert result.written, result.error
    monkeypatch.undo()
    assert _tags(path)["summary"] == "New"
    assert _leftovers(tmp_path) == set()


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


# ------------------------------------------------------------ kill and replay


def _killed_write(
    monkeypatch: pytest.MonkeyPatch, path: Path
) -> tuple[bytes, bytes, bytes]:
    """
    Make a write and keep its journal, as a kill before its delete leaves it.

    Return the archive before and after, and the journal.
    """
    original = path.read_bytes()
    seen: dict[str, bytes] = {}
    real_finish = TailJournal._finish

    def keep(self: TailJournal) -> None:
        seen["journal"] = journal_path(path).read_bytes()
        real_finish(self)

    monkeypatch.setattr(TailJournal, "_finish", keep)
    assert _retag(path).written
    monkeypatch.undo()
    return original, path.read_bytes(), seen["journal"]


def _header(journal: bytes) -> dict[str, Any]:
    return json.loads(journal.split(b"\n", 2)[1])


def _with_writer(journal: bytes, **writer: Any) -> bytes:
    magic, header, tail = journal.split(b"\n", 2)
    fields = {**json.loads(header), **writer}
    return b"\n".join((magic, json.dumps(fields).encode(), tail))


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _states(original: bytes, final: bytes, offset: int) -> dict[str, bytes]:
    """List the archive as a kill at several points of the tail write leaves it."""
    tail = len(final) - offset
    states: dict[str, bytes] = {}
    for name, cut in (("start", 0), ("one byte", 1), ("half", tail // 2)):
        states[f"cut at {name}"] = final[: offset + cut]
        states[f"overwritten to {name}"] = (
            final[: offset + cut] + original[offset + cut :]
        )
    states["written, journal not yet deleted"] = final
    return states


@pytest.fixture
def killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, bytes, dict[str, bytes], bytes]:
    path = _comic(tmp_path)
    original, final, journal = _killed_write(monkeypatch, path)
    offset = _header(journal)["offset"]
    assert final[:offset] == original[:offset]
    dead = _with_writer(journal, pid=_dead_pid())
    return path, original, _states(original, final, offset), dead


@pytest.mark.parametrize("how", ["read", "write"])
def test_a_killed_write_is_undone_when_the_comic_is_next_opened(
    killed: tuple[Path, bytes, dict[str, bytes], bytes], how: str
) -> None:
    path, original, states, journal = killed
    for name, state in states.items():
        path.write_bytes(state)
        journal_path(path).write_bytes(journal)

        if how == "read":
            assert _tags(path).get("summary") is None, name
            assert path.read_bytes() == original, name
        else:
            assert _retag(path, "Again").written, name
            assert _tags(path)["summary"] == "Again", name
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None, name
        assert not journal_path(path).exists(), name


def test_a_journal_from_another_host_is_replayed(
    killed: tuple[Path, bytes, dict[str, bytes], bytes],
) -> None:
    path, original, states, journal = killed
    path.write_bytes(states["cut at half"])
    journal_path(path).write_bytes(
        _with_writer(journal, host="elsewhere", pid=os.getpid())
    )

    _tags(path)

    assert path.read_bytes() == original


def test_a_journal_whose_writer_is_alive_is_refused(
    killed: tuple[Path, bytes, dict[str, bytes], bytes],
) -> None:
    path, _original, states, journal = killed
    state = states["cut at half"]
    path.write_bytes(state)
    journal_path(path).write_bytes(_with_writer(journal, pid=os.getpid()))

    with pytest.raises(DestinationOccupiedError) as exc_info:
        Comicbox(path)
    result = _retag(path)

    assert exc_info.value.kind == "writing"
    assert isinstance(result.error, DestinationOccupiedError)
    assert path.read_bytes() == state
    assert journal_path(path).exists()


@pytest.mark.parametrize("mismatch", ["pages changed", "not a journal"])
def test_a_journal_that_does_not_fit_is_left_alone(
    killed: tuple[Path, bytes, dict[str, bytes], bytes], mismatch: str
) -> None:
    path, original, _, journal = killed
    if mismatch == "pages changed":
        # The comic was replaced since: its last page differs.
        offset = _header(journal)["offset"]
        state = bytearray(original)
        state[offset - 10] ^= 0xFF
        state = bytes(state)
    else:
        state, journal = original, b"something else"
    path.write_bytes(state)
    journal_path(path).write_bytes(journal)

    Comicbox(path).close()

    assert path.read_bytes() == state
    assert journal_path(path).read_bytes() == journal


# ------------------------------------------------------------ the copy path


def _tags_first(tmp_path: Path) -> Path:
    """ComicInfo.xml stored before the pages, as some other tools write it."""
    path = tmp_path / "first.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "ComicInfo.xml", "<ComicInfo><Series>Civil War</Series></ComicInfo>"
        )
        _pages(archive)
    return path


def test_a_tags_first_archive_is_copied_once_then_patched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _tags_first(tmp_path)
    copies: list[Path] = []
    real_create = write_module.ComicboxArchiveWrite._create_zipfile

    def spy(self: Any, *args: Any, **kwargs: Any) -> None:
        copies.append(self._path)
        real_create(self, *args, **kwargs)

    monkeypatch.setattr(write_module.ComicboxArchiveWrite, "_create_zipfile", spy)

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
    """Record the comic-suffixed names in a directory at each step of a write."""
    seen: list[set[str]] = []

    def watching(owner: Any, name: str) -> None:
        real = getattr(owner, name)

        def fake(*args: Any, **kwargs: Any) -> Any:
            seen.append(_comic_files(directory))
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, fake)

    watching(zipfile.ZipFile, "writestr")
    watching(journal_module, "_flush")
    watching(write_module.ComicboxArchiveWrite, "_cleanup_tmp_archive")
    return lambda: seen


@pytest.mark.parametrize("archive", ["tail", "tags first", "cbt"])
def test_no_comic_named_file_appears_during_a_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, archive: str
) -> None:
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
    before = _comic_files(tmp_path)
    seen = _watch_names(monkeypatch, tmp_path)

    assert _retag(path).written

    monkeypatch.undo()
    assert seen()
    assert all(names == before for names in seen())


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
def test_the_journal_changes_no_byte_of_a_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    formats: list[str],
    patch: dict[str, Any],
) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    journaled = _comic(tmp_path / "journaled")
    plain = _comic(tmp_path / "plain")
    assert journaled.read_bytes() == plain.read_bytes()

    assert write_metadata(journaled, patch, formats=formats).written

    @contextmanager
    def no_journal(*_args: Any) -> Generator[None]:
        yield

    monkeypatch.setattr(write_module, "TailJournal", no_journal)
    assert write_metadata(plain, patch, formats=formats).written

    assert journaled.read_bytes() == plain.read_bytes()


def test_a_link_and_its_file_share_one_journal(tmp_path: Path) -> None:
    path = _comic(tmp_path / "real")
    link = tmp_path / "link.cbz"
    link.symlink_to(path)

    assert journal_path(link) == journal_path(path)
    assert journal_path(path).parent == path.parent
