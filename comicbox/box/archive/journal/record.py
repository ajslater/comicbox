"""A journal's names, its contents, and whether it is in flight."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import stat
import sys
import time
from dataclasses import asdict, dataclass, fields
from threading import Lock
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, BinaryIO, get_type_hints

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

JOURNAL_SUFFIX = ".comicbox-journal.tmp"
# A journal a process has claimed to settle it: as long a name as the journal's.
CLAIMED_SUFFIX = ".comicbox-claimed.tmp"
#: A write whose tail is larger than this copies the archive instead.
TAIL_CAP = 16 * 1024 * 1024
#: A journal younger than this, by another live writer here or by any writer
#: on another host, is a write in flight; an older one is stale.
IN_FLIGHT_AGE = 5 * 60
MAGIC = b"comicbox-journal 1\n"
_NOT_OWED = b'"rollback": 0'
# The bytes before the tail whose checksum the journal keeps.
BEFORE_SIZE = 64 * 1024
_MAX_HEADER_SIZE = 4096
# The longest file name most filesystems take, in bytes, and the length of
# the hash that stands in for a comic's name past it.
_NAME_MAX = 255
_SHORT_DIGEST = 32
# Lookups that find no journal there: nothing, a name too long, a non-directory.
_NO_JOURNAL = frozenset({errno.ENOENT, errno.ENAMETOOLONG, errno.ENOTDIR, errno.EISDIR})
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)

# The journals this process is writing now. In flight is known from this
# record, not from the process id, so a journal a failed rollback left behind
# is stale to the process that wrote it.
_OPEN: set[str] = set()
_OPEN_GUARD = Lock()


def hidden_name(name: str, suffix: str) -> str:
    """
    Name a hidden file beside a comic: ``.<name><suffix>``.

    Where that is longer than a directory takes (255 bytes), a hash of the
    comic's name stands in for it, still dot-named and ending ``suffix``, so
    a long-named comic still gets its journal and its temporary archive.
    Each comic has one name or the other, so a look costs the same.
    """
    full = f".{name}{suffix}"
    if len(os.fsencode(full)) <= _NAME_MAX:
        return full
    digest = hashlib.sha256(os.fsencode(name)).hexdigest()[:_SHORT_DIGEST]
    return f".{digest}{suffix}"


def journal_path(path: Path) -> Path:
    """
    Name an archive's journal: beside the file itself.

    Through a link, that is beside the link's target, so every name a comic
    is opened by finds the one journal. A linked directory needs no
    resolving, which is most of what a check costs: the file's name in it
    is the file's own.
    """
    real = path.resolve() if path.is_symlink() else path
    return real.with_name(hidden_name(real.name, JOURNAL_SUFFIX))


def claimed_path(journal: Path) -> Path:
    """Name the journal once a process has claimed it."""
    stem = journal.name.removesuffix(JOURNAL_SUFFIX)
    return journal.with_name(f"{stem}{CLAIMED_SUFFIX}")


@dataclass(frozen=True, slots=True)
class Header:
    """What a journal says of the write it was taken for."""

    length: int
    offset: int
    tail_sha256: str
    before_offset: int
    before_sha256: str
    host: str
    pid: int
    # 1 once its writer's rollback failed: it owes one, and is replayed
    # whether or not the archive verifies. Written 0, so it is set in place.
    rollback: int

    def to_bytes(self) -> bytes:
        """Render the marker and header lines."""
        return MAGIC + json.dumps(asdict(self)).encode() + b"\n"


# Each header field's type, resolved from the annotations above.
_HEADER_TYPES: MappingProxyType[str, Any] = MappingProxyType(get_type_hints(Header))


@dataclass(frozen=True, slots=True)
class Found:
    """A journal as read from disk, with its header if it has one."""

    data: bytes
    mtime: float
    header: Header | None
    tail: bytes


def sha256(data: bytes) -> str:
    """Hash bytes for a journal."""
    return hashlib.sha256(data).hexdigest()


def read_range(archive: BinaryIO, start: int, size: int) -> bytes:
    """Read ``size`` bytes from ``start``."""
    archive.seek(start)
    return archive.read(size)


def flush(stream: BinaryIO) -> None:
    """Flush a stream to disk."""
    stream.flush()
    os.fsync(stream.fileno())


def restore(path: Path, offset: int, tail: bytes, length: int) -> None:
    """Write an old tail back and cut the archive to its old length."""
    with path.open("r+b") as archive:
        archive.seek(offset)
        archive.write(tail)
        archive.truncate(length)
        flush(archive)


def opened(journal: Path) -> None:
    """Record a journal this process is writing."""
    with _OPEN_GUARD:
        _OPEN.add(str(journal))


def closed(journal: Path) -> None:
    """Forget a journal this process was writing."""
    with _OPEN_GUARD:
        _OPEN.discard(str(journal))


def _parse(data: bytes) -> tuple[Header | None, bytes]:
    """
    Read a journal's header and its tail; no header where it has none.

    A header whose fields are not the types it declares is none: an integer
    is an integer, not ``"1234"`` and not a boolean.
    """
    if not data.startswith(MAGIC):
        return None, b""
    end = data.find(b"\n", len(MAGIC), len(MAGIC) + _MAX_HEADER_SIZE)
    if end < 0:
        return None, b""
    try:
        raw: Any = json.loads(data[len(MAGIC) : end])
        values = {field.name: raw[field.name] for field in fields(Header)}
    except (ValueError, TypeError, KeyError):
        return None, b""
    if any(type(values[name]) is not kind for name, kind in _HEADER_TYPES.items()):
        return None, b""
    return Header(**values), data[end + 1 :]


def read_journal(journal: Path, path: Path) -> Found | None:
    """
    Read a journal; None where there is no usable one.

    Nothing there, a name too long to look up, or a directory or other
    non-file at its name is no journal. One that cannot be read is none
    either, with a warning. A lookup is one failed open.
    """
    try:
        fd = os.open(journal, _READ_FLAGS)
    except OSError as exc:
        if exc.errno not in _NO_JOURNAL:
            logger.warning(f"{path}: cannot read {journal.name}: {exc}")
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            return None
        try:
            data = stream.read()
        except OSError as exc:
            logger.warning(f"{path}: cannot read {journal.name}: {exc}")
            return None
    header, tail = _parse(data)
    return Found(data, info.st_mtime, header, tail)


def _writer_named(header: Header) -> bool:
    return header.pid > 0


def owes_rollback(found: Found) -> bool:
    """Tell whether a journal's writer failed to roll its write back."""
    return found.header is not None and found.header.rollback == 1


def mark_owed(journal: Path) -> bool:
    """
    Mark a journal as owing a rollback, in place; whether it could be.

    One byte of its header changes, so an open that finds nothing there
    pays nothing for it, and a later process can read it.
    """
    try:
        with journal.open("r+b") as stream:
            head = stream.read(len(MAGIC) + _MAX_HEADER_SIZE)
            if (at := head.find(_NOT_OWED)) < 0:
                return False
            stream.seek(at + len(_NOT_OWED) - 1)
            stream.write(b"1")
            flush(stream)
    except OSError:
        return False
    return True


def is_valid(found: Found) -> bool:
    """
    Tell whether a journal is whole and right, so a write may be undone by it.

    Its numbers are non-negative integers that fit together, its writer is
    named, and its tail is the length it says with the checksum it says.
    """
    header = found.header
    if header is None or not _writer_named(header):
        return False
    return (
        header.rollback in (0, 1)
        and 0 <= header.before_offset <= header.offset <= header.length
        and header.length - header.offset == len(found.tail) <= TAIL_CAP
        and sha256(found.tail) == header.tail_sha256
    )


def _windows_pid_alive(pid: int) -> bool:  # pragma: no cover
    import ctypes

    # os.kill(pid, 0) would end the process on Windows.
    kernel32 = ctypes.windll.kernel32  # ty: ignore[missing-attribute]
    query_limited_information, still_active, access_denied = 0x1000, 259, 5
    handle = kernel32.OpenProcess(query_limited_information, False, pid)  # noqa: FBT003
    if not handle:
        return kernel32.GetLastError() == access_denied
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_young(found: Found) -> bool:
    """Tell whether a journal or a claim was made under five minutes ago."""
    return time.time() - found.mtime < IN_FLIGHT_AGE


def in_flight(journal: Path, found: Found) -> bool:
    """
    Tell whether a journal is a write going on now.

    This process's own open journals are; so is one under five minutes old
    whose writer is another live process on this host, or any process on
    another host. A journal that names no writer is not: it has no header,
    so it was never complete, and the archive was never touched under it.
    """
    with _OPEN_GUARD:
        if str(journal) in _OPEN:
            return True
    header = found.header
    if header is None or not _writer_named(header) or not is_young(found):
        return False
    if header.rollback:
        # Its writer gave up on it: that write is over.
        return False
    if header.host != socket.gethostname():
        return True
    return header.pid != os.getpid() and _pid_alive(header.pid)
