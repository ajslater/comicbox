"""Whether an archive is whole: what decides a stale journal's fate."""

from __future__ import annotations

import os
import struct
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from comicbox.box.archive.journal.record import read_range, sha256
from comicbox.box.archive.tag_names import ALL_ARCHIVE_METADATA_FILENAMES

if TYPE_CHECKING:
    from comicbox.box.archive.journal.record import Header

_LOCAL = struct.Struct("<4s2B4HL2L2H")
_LOCAL_SIGNATURE = b"PK\x03\x04"
_END_SIGNATURE = b"PK\x05\x06"
_END_SIZE = 22
_END_COMMENT_SIZE = slice(20, 22)
_DATA_DESCRIPTOR = 0x08
_ZIP64_SIZE = 0xFFFFFFFF
_BROKEN = (
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    OSError,
    ValueError,
    EOFError,
    NotImplementedError,
    RuntimeError,
    struct.error,
)


def _ends_the_file(raw: BinaryIO, comment: bytes) -> bool:
    """
    Tell whether the end record and its comment end the file.

    A write killed between writing a shorter end record and cutting the file
    leaves old bytes after it, which a zip reader skips over.
    """
    end = raw.seek(0, os.SEEK_END)
    start = end - _END_SIZE - len(comment)
    if start < 0:
        return False
    raw.seek(start)
    record = raw.read(_END_SIZE)
    size = int.from_bytes(record[_END_COMMENT_SIZE], "little")
    return record[:4] == _END_SIGNATURE and size == len(comment)


def _header_agrees(raw: BinaryIO, info: zipfile.ZipInfo) -> bool:
    """Tell whether a member's local header says what the directory does."""
    raw.seek(info.header_offset)
    signature, _, _, flags, method, _, _, crc, size, *_ = _LOCAL.unpack(
        raw.read(_LOCAL.size)
    )
    if signature != _LOCAL_SIGNATURE or method != info.compress_type:
        return False
    if flags & _DATA_DESCRIPTOR or size == _ZIP64_SIZE:
        # The sizes and checksum follow the data, or live in zip64 fields.
        return True
    return (crc, size) == (info.CRC, info.compress_size)


def _member_whole(
    archive: zipfile.ZipFile, raw: BinaryIO, info: zipfile.ZipInfo, tags: frozenset[str]
) -> bool:
    if not _header_agrees(raw, info):
        return False
    # Opening checks the local name against the directory's; reading a tag
    # file checks its CRC. Pages are not read.
    with archive.open(info) as member:
        if Path(info.filename).name.lower() in tags:
            member.read()
    return True


def verifies(path: Path) -> bool:
    """
    Tell whether an archive is whole.

    Its end record and central directory parse and end the file, every
    member's local header agrees with the directory, and every tag file
    passes its CRC.
    """
    tags = ALL_ARCHIVE_METADATA_FILENAMES
    try:
        with zipfile.ZipFile(path) as archive, path.open("rb") as raw:
            return _ends_the_file(raw, archive.comment) and all(
                _member_whole(archive, raw, info, tags) for info in archive.infolist()
            )
    except _BROKEN:
        return False


def fits(path: Path, header: Header) -> bool:
    """Tell whether the bytes before a journal's tail are the archive's."""
    size = header.offset - header.before_offset
    try:
        with path.open("rb") as archive:
            long_enough = archive.seek(0, os.SEEK_END) >= header.offset
            before = read_range(archive, header.before_offset, size)
    except OSError:
        return False
    return (
        long_enough and len(before) == size and sha256(before) == header.before_sha256
    )
