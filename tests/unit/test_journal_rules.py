"""
What opening a comic does with a journal beside it (D1, section 10).

One test per line of D1's "What that decides", and the tests the review found
missing. Every archive is generated under tmp_path; a live writer is a real
process other than the test's own.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import random
import subprocess
import sys
import time
import zipfile
from argparse import Namespace
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.box.archive.journal import TailJournal, journal_path, replay_journal
from comicbox.box.archive.journal import tail as tail_module
from comicbox.box.archive.journal.record import claimed_path
from comicbox.config import get_config
from comicbox.exceptions import DestinationOccupiedError, UnsupportedArchiveTypeError
from comicbox.write import write_metadata

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"
_TAGS: dict[str, Any] = {"series": {"name": "Civil War"}, "issue": {"name": "1"}}
_OLD = 10 * 60


def _page(seed: int) -> bytes:
    # Seeded, so two copies of a comic are the same bytes: test data only.
    return random.Random(seed).randbytes(50_000)  # noqa: S311


def _comic(tmp_path: Path, name: str = "comic.cbz", *, pages: int = 3) -> Path:
    """Pages, then ComicInfo and MetronInfo, as comicbox writes them."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(pages):
            archive.writestr(f"page-{index}.jpg", _page(index))
    assert write_metadata(path, _TAGS, formats=[_CIX, _MI]).written
    return path


def _retag(path: Path, summary: str = "New") -> Any:
    return write_metadata(path, {"summary": summary}, formats=[_CIX, _MI])


def _summary(path: Path) -> str | None:
    with Comicbox(path) as box:
        return box.to_dict()["comicbox"].get("summary")


def _killed(monkeypatch: pytest.MonkeyPatch, path: Path) -> tuple[bytes, bytes, bytes]:
    """
    Make a write, keeping its journal as a kill before the delete leaves it.

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


def _offset(journal: bytes) -> int:
    return json.loads(journal.split(b"\n", 2)[1])["offset"]


def _with(journal: bytes, **header: Any) -> bytes:
    """Rewrite a journal's header fields; its tail is left as it is."""
    magic, raw, tail = journal.split(b"\n", 2)
    return b"\n".join((magic, json.dumps({**json.loads(raw), **header}).encode(), tail))


def _place(path: Path, state: bytes, journal: bytes, *, age: float = 0) -> Path:
    path.write_bytes(state)
    journal_file = journal_path(path)
    journal_file.write_bytes(journal)
    if age:
        then = time.time() - age
        os.utime(journal_file, (then, then))
    return journal_file


def _mid_tail(original: bytes, final: bytes, journal: bytes) -> bytes:
    """Cut the archive as a kill half way through the tail write leaves it."""
    offset = _offset(journal)
    return final[: offset + (len(final) - offset) // 2]


@pytest.fixture
def live_pid() -> Iterator[int]:
    """Run a live process on this host that is not the test's own."""
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield sleeper.pid
    finally:
        sleeper.kill()
        sleeper.wait()


@pytest.fixture
def warnings(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    handler_id = logger.add(caplog.handler, level=0)
    caplog.set_level(logging.WARNING)
    try:
        yield caplog
    finally:
        logger.remove(handler_id)


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


@contextmanager
def _read_only(directory: Path) -> Generator[None]:
    mode = directory.stat().st_mode
    directory.chmod(0o555)
    try:
        yield
    finally:
        directory.chmod(mode)


_POSIX = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions"
)


# ------------------------------------------------------------------ names


@pytest.mark.parametrize("length", [234, 255])
def test_a_comic_with_a_long_name_opens_and_takes_a_write(
    tmp_path: Path, length: int
) -> None:
    """Every open failed with "File name too long": the journal's name is."""
    path = _comic(tmp_path, "c" * (length - 4) + ".cbz")

    assert _retag(path).written
    assert _summary(path) == "New"
    assert {p.name for p in tmp_path.iterdir()} == {path.name}


# ----------------------------------------------------------------- kills


@pytest.mark.parametrize("how", ["read", "write"])
def test_a_write_killed_before_its_journal_was_deleted_keeps_its_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str
) -> None:
    path = _comic(tmp_path)
    _, final, journal = _killed(monkeypatch, path)
    journal_file = _place(path, final, journal)

    if how == "write":
        assert _retag(path, "Again").written
        assert _summary(path) == "Again"
    else:
        assert _summary(path) == "New"
        assert path.read_bytes() == final
    assert not journal_file.exists()


@pytest.mark.parametrize("how", ["read", "write"])
@pytest.mark.parametrize(
    "cut", ["at the start", "one byte in", "half way", "overwritten"]
)
def test_a_write_killed_mid_tail_is_undone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cut: str, how: str
) -> None:
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    offset = _offset(journal)
    half = offset + (len(final) - offset) // 2
    state = {
        "at the start": final[:offset],
        "one byte in": final[: offset + 1],
        "half way": final[:half],
        "overwritten": final[:half] + original[half:],
    }[cut]
    journal_file = _place(path, state, journal)

    if how == "write":
        assert _retag(path, "Again").written
        assert _summary(path) == "Again"
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
    else:
        assert _summary(path) is None
        assert path.read_bytes() == original
    assert not journal_file.exists()
    assert not claimed_path(journal_file).exists()


def test_a_comic_replaced_since_its_write_was_killed_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tag-only comic's journal overwrote the full comic put in its place."""
    path = _comic(tmp_path / "tags", pages=0)
    _, _, journal = _killed(monkeypatch, path)
    full = _comic(tmp_path / "full").read_bytes()
    journal_file = _place(path, full, journal)

    assert _summary(path) is None

    assert path.read_bytes() == full
    assert not journal_file.exists()


def test_another_tools_tags_after_a_kill_are_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _comic(tmp_path)
    _, final, journal = _killed(monkeypatch, path)
    path.write_bytes(final)
    with zipfile.ZipFile(path, "a") as archive:
        for name in ("ComicInfo.xml", "MetronInfo.xml"):
            archive.remove(name)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
        archive.repack()  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
        archive.writestr(
            "ComicInfo.xml", "<ComicInfo><Summary>Other</Summary></ComicInfo>"
        )
    other = path.read_bytes()
    journal_file = _place(path, other, journal)

    assert _summary(path) == "Other"
    assert path.read_bytes() == other
    assert not journal_file.exists()


# -------------------------------------------------------- whose journal


@pytest.mark.parametrize("writer", ["process 1", "another live process"])
def test_a_live_writers_journal_is_refused_until_it_is_old(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, live_pid: int, writer: str
) -> None:
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    pid = 1 if writer == "process 1" else live_pid
    state = _mid_tail(original, final, journal)
    journal_file = _place(path, state, _with(journal, pid=pid))

    with pytest.raises(DestinationOccupiedError) as refused:
        Comicbox(path)
    assert isinstance(_retag(path).error, DestinationOccupiedError)
    assert refused.value.kind == "writing"
    assert path.read_bytes() == state

    then = time.time() - _OLD
    os.utime(journal_file, (then, then))
    assert _summary(path) is None
    assert path.read_bytes() == original
    assert not journal_file.exists()


def test_a_recent_journal_from_another_host_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    state = _mid_tail(original, final, journal)
    _place(path, state, _with(journal, host="elsewhere"))

    with pytest.raises(DestinationOccupiedError):
        Comicbox(path)

    _place(path, state, _with(journal, host="elsewhere"), age=_OLD)
    Comicbox(path).close()
    assert path.read_bytes() == original


def test_this_processs_failed_rollback_is_replayed_on_its_next_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The comic was refused for the life of the process that wrote it."""
    path = _comic(tmp_path)
    original = path.read_bytes()

    def end_record(self: zipfile.ZipFile) -> None:
        assert self.fp is not None
        self.fp.flush()
        raise OSError(errno.EIO, "the disk went away")

    def restore(*_args: Any) -> None:
        raise OSError(errno.EIO, "still away")

    monkeypatch.setattr(zipfile.ZipFile, "_write_end_record", end_record)
    monkeypatch.setattr(tail_module, "restore", restore)
    assert not _retag(path).written
    monkeypatch.undo()
    assert journal_path(path).exists()
    assert path.read_bytes() != original

    assert _summary(path) is None
    assert path.read_bytes() == original
    assert not journal_path(path).exists()


# -------------------------------------------------------- what a journal is


def test_a_journal_a_kill_cut_short_is_removed_and_the_next_write_journals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """It was "left alone" for ever, and every later write ran without one."""
    path = _comic(tmp_path)
    original, _, journal = _killed(monkeypatch, path)
    journal_file = _place(path, original, journal[: len(journal) // 2])

    assert _summary(path) is None
    assert not journal_file.exists()
    assert path.read_bytes() == original

    journaled: list[bool] = []
    real_finish = TailJournal._finish

    def finish(self: TailJournal) -> None:
        journaled.append(journal_file.exists())
        real_finish(self)

    monkeypatch.setattr(TailJournal, "_finish", finish)
    assert _retag(path, "Next").written
    assert journaled == [True]


@pytest.mark.parametrize(
    "header",
    [{"offset": "1234"}, {"pid": 0}, {"pid": -1}],
    ids=["offset a string", "pid 0", "pid -1"],
)
def test_a_malformed_header_is_an_invalid_journal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, header: dict[str, Any]
) -> None:
    """Not a traceback, and not a write in progress."""
    path = _comic(tmp_path)
    original, _, journal = _killed(monkeypatch, path)
    journal_file = _place(path, original, _with(journal, **header))

    assert _summary(path) is None

    assert path.read_bytes() == original
    assert not journal_file.exists()


def test_a_tail_that_fails_its_checksum_is_never_replayed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, warnings: pytest.LogCaptureFixture
) -> None:
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    state = _mid_tail(original, final, journal)
    rotten = bytearray(journal)
    rotten[-5] ^= 0xFF
    journal_file = _place(path, state, bytes(rotten))

    assert not replay_journal(path)

    assert path.read_bytes() == state
    assert not journal_file.exists()
    assert "is damaged" in _messages(warnings)


# --------------------------------------------------------- two processes


_SLOW_SETTLE = """
import sys, time
from pathlib import Path
from comicbox.box.archive.journal import replay
real = replay._settle
def slow(*args, **kwargs):
    time.sleep(1.5)
    return real(*args, **kwargs)
replay._settle = slow
from comicbox.box import Comicbox
Comicbox(Path(sys.argv[1])).close()
"""


def test_two_processes_meet_one_stale_journal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One replays it; the other is refused while it does."""
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    # Old, or the other process would count this live test's journal in flight.
    journal_file = _place(path, _mid_tail(original, final, journal), journal, age=_OLD)
    claimed = claimed_path(journal_file)

    other = subprocess.Popen([sys.executable, "-c", _SLOW_SETTLE, str(path)])  # noqa: S603
    deadline = time.monotonic() + 20
    while not claimed.exists() and other.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        assert claimed.exists()
        with pytest.raises(DestinationOccupiedError):
            Comicbox(path)
    finally:
        assert other.wait(timeout=30) == 0

    assert path.read_bytes() == original
    assert not journal_file.exists()
    assert not claimed.exists()


def test_a_claim_that_takes_a_newer_journal_gives_it_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, live_pid: int
) -> None:
    """
    Another process settled the journal and began a write before the claim.

    The claim then holds that write's journal; replaying it would undo the
    write. It is given back, and the comic refused.
    """
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    state = _mid_tail(original, final, journal)
    journal_file = _place(path, state, journal)
    newer = _with(journal, pid=live_pid)
    real_utime = os.utime

    def meanwhile(target: Any, *args: Any, **kwargs: Any) -> None:
        if str(target) == str(journal_file):
            journal_file.write_bytes(newer)
        real_utime(target, *args, **kwargs)

    monkeypatch.setattr(os, "utime", meanwhile)
    with pytest.raises(DestinationOccupiedError):
        Comicbox(path)
    monkeypatch.undo()

    assert path.read_bytes() == state
    assert journal_file.read_bytes() == newer
    assert not claimed_path(journal_file).exists()


def test_a_journal_that_appears_before_a_write_refuses_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, live_pid: int
) -> None:
    """The comic opened without one; another writer began before this one."""
    path = _comic(tmp_path)
    _, final, journal = _killed(monkeypatch, path)
    real_enter = TailJournal.__enter__

    def enter(self: TailJournal) -> TailJournal:
        journal_path(path).write_bytes(_with(journal, pid=live_pid))
        return real_enter(self)

    monkeypatch.setattr(TailJournal, "__enter__", enter)
    result = _retag(path, "Rival")
    monkeypatch.undo()

    assert isinstance(result.error, DestinationOccupiedError)
    assert path.read_bytes() == final


# ------------------------------------------------------ where it cannot act


@_POSIX
def test_a_stale_journal_in_a_read_only_directory_beside_a_whole_comic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, warnings: pytest.LogCaptureFixture
) -> None:
    directory = tmp_path / "ro"
    path = _comic(directory)
    _, final, journal = _killed(monkeypatch, path)
    journal_file = _place(path, final, journal)

    with _read_only(directory):
        assert _summary(path) == "New"

    assert journal_file.exists()
    assert "cannot remove" in _messages(warnings)


def test_a_dry_run_beside_a_damaged_comic_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _comic(tmp_path)
    original, final, journal = _killed(monkeypatch, path)
    state = _mid_tail(original, final, journal)
    journal_file = _place(path, state, journal)

    with pytest.raises(SystemExit):
        cli.main(("comicbox", "-n", "-p", str(path)))
    dry = get_config(Namespace(comicbox=Namespace(**{"general.dry_run": True})))
    # The damaged comic is opened as it is, and is not a zip.
    with suppress(UnsupportedArchiveTypeError):
        Comicbox(path, config=dry).close()

    assert path.read_bytes() == state
    assert journal_file.read_bytes() == journal


# ------------------------------------------------------- the tail itself


def test_an_orphaned_entry_before_the_tail_is_left_in_place(tmp_path: Path) -> None:
    """A bare repack() also strips it, and slides every later page down."""
    path = tmp_path / "orphan.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(3):
            archive.writestr(f"page-{index}.jpg", _page(index))
    with zipfile.ZipFile(path, "a") as archive:
        # Out of the directory; its local entry stays in the file.
        archive.remove("page-1.jpg")  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
    before = path.read_bytes()

    assert write_metadata(path, _TAGS, formats=[_CIX]).written

    assert path.read_bytes()[:start_dir] == before[:start_dir]
