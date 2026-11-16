"""
A zip that cannot be patched in place is patched on a copy (D2, section 10).

A tags-first comic, or one whose tail is over the cap, went through the CBR
conversion path, which renamed a member without a suffix, merged two members
of one name, dropped directory entries and member dates, modes and comments,
read every page, and through a link replaced the link. Now the in-place write
runs on a copy of the real file, which then replaces it.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import time
import warnings
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.box.archive import write as write_module
from comicbox.write import write_metadata

if TYPE_CHECKING:
    from collections.abc import Callable

_CIX = "COMIC_INFO"
_TAGS = frozenset({"comicinfo.xml", "metroninfo.xml"})
_FIRST_CIX = "<ComicInfo><Series>Civil War</Series></ComicInfo>"


_Date = tuple[int, int, int, int, int, int]


def _member(
    name: str, date: _Date, mode: int = 0o644, comment: bytes = b""
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=date)
    info.external_attr = (mode | stat.S_IFREG) << 16
    info.comment = comment
    info.compress_type = (
        zipfile.ZIP_DEFLATED if name.endswith(".txt") else zipfile.ZIP_STORED
    )
    return info


def _odd_zip(path: Path) -> Path:
    """ComicInfo first, then the members the conversion path mangled."""
    with zipfile.ZipFile(path, "w") as archive, warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # the duplicate name
        archive.writestr("ComicInfo.xml", _FIRST_CIX)
        archive.writestr(_member("LICENSE", (2001, 2, 3, 4, 5, 6)), b"the license")
        directory = zipfile.ZipInfo("extras/", date_time=(2002, 1, 1, 0, 0, 0))
        directory.external_attr = (0o755 | stat.S_IFDIR) << 16 | 0x10
        archive.writestr(directory, b"")
        archive.writestr(
            _member("page001.jpg", (2003, 1, 1, 0, 0, 0)), b"first page bytes"
        )
        archive.writestr(
            _member("page001.jpg", (2003, 1, 1, 0, 0, 2)), b"second page bytes"
        )
        archive.writestr(
            _member(
                "notes.txt", (1999, 12, 31, 23, 59, 58), 0o600, b"a member comment"
            ),
            b"the scanner's notes",
        )
    return path


def _members(path: Path) -> list[tuple[Any, ...]]:
    """Every member but a tag file: what the write must leave as it was."""
    with zipfile.ZipFile(path) as archive:
        return [
            (
                info.filename,
                info.date_time,
                info.external_attr,
                info.comment,
                info.compress_type,
                info.CRC,
                archive.open(info).read(),
            )
            for info in archive.infolist()
            if Path(info.filename).name.lower() not in _TAGS
        ]


def _summary(path: Path) -> str | None:
    with Comicbox(path) as box:
        return box.to_dict()["comicbox"].get("summary")


def _retag(path: Path, summary: str = "New") -> Any:
    return write_metadata(path, {"summary": summary}, formats=[_CIX])


def _leftovers(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if p.name.startswith(".")}


def test_every_other_member_is_kept_as_it_was(tmp_path: Path) -> None:
    path = _odd_zip(tmp_path / "odd.cbz")
    before = _members(path)

    assert _retag(path).written

    assert _members(path) == before
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist()[-1] == "ComicInfo.xml"
    assert _summary(path) == "New"
    assert _leftovers(tmp_path) == set()


def test_through_a_link_the_real_comic_is_written(tmp_path: Path) -> None:
    """The link was replaced by a regular file, and the comic left untagged."""
    (tmp_path / "real").mkdir()
    real = _odd_zip(tmp_path / "real" / "comic.cbz")
    link = tmp_path / "link.cbz"
    link.symlink_to(real)

    assert _retag(link).written

    assert link.is_symlink()
    assert link.resolve() == real.resolve()
    assert _summary(real) == "New"
    assert _leftovers(real.parent) == set()


def test_the_mode_is_kept(tmp_path: Path) -> None:
    path = _odd_zip(tmp_path / "odd.cbz")
    path.chmod(0o600)

    assert _retag(path).written

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_comic_with_a_damaged_page_can_be_tagged(tmp_path: Path) -> None:
    """Every page was read, so one bad CRC stopped the comic being tagged."""
    path = _odd_zip(tmp_path / "odd.cbz")
    data = bytearray(path.read_bytes())
    where = data.index(b"first page bytes")
    data[where] ^= 0xFF
    path.write_bytes(bytes(data))

    assert _retag(path).written

    assert _summary(path) == "New"
    with zipfile.ZipFile(path) as archive:
        # By its own entry: testzip reads by name, which finds the second.
        damaged = next(i for i in archive.infolist() if i.filename == "page001.jpg")
        with pytest.raises(zipfile.BadZipFile):
            archive.read(damaged)


def _in_place_offset(self: Any, path: Path, rewritten: frozenset[str] | None) -> int:
    """Patch in place whatever the layout, as the write did before the copy path."""
    with zipfile.ZipFile(path) as archive:
        removed = [
            info.header_offset
            for info in archive.infolist()
            if self._is_replaced(info.filename, rewritten)
        ]
        return min((*removed, archive.start_dir))


def test_the_copy_gives_the_in_place_writes_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    copied = _odd_zip(tmp_path / "copied.cbz")
    in_place = _odd_zip(tmp_path / "in_place.cbz")
    assert copied.read_bytes() == in_place.read_bytes()

    assert _retag(copied).written
    monkeypatch.setattr(
        write_module.ComicboxArchiveWrite, "_tail_offset", _in_place_offset
    )
    assert _retag(in_place).written

    assert copied.read_bytes() == in_place.read_bytes()


def _fail(
    monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, when: Callable[..., bool]
) -> None:
    real = getattr(owner, name)

    def fake(*args: Any, **kwargs: Any) -> Any:
        if when(*args):
            raise OSError(errno.EIO, "the disk went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, fake)


@pytest.mark.parametrize("step", ["writing the copy", "the final replace"])
def test_a_failure_leaves_the_comic_and_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: str
) -> None:
    path = _odd_zip(tmp_path / "odd.cbz")
    original = path.read_bytes()
    if step == "writing the copy":
        _fail(monkeypatch, zipfile.ZipFile, "writestr", lambda *_: True)
    else:
        _fail(
            monkeypatch,
            Path,
            "replace",
            lambda source, *_: source.name.endswith(".tmp"),
        )

    assert not _retag(path).written

    monkeypatch.undo()
    assert path.read_bytes() == original
    assert _leftovers(tmp_path) == set()


def test_a_tail_over_the_cap_is_written_on_a_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "comic.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("page-0.jpg", os.urandom(1000))
    assert _retag(path, "First").written
    copies: list[Path] = []
    real_copy = write_module.ComicboxArchiveWrite._patch_a_copy

    def spy(self: Any, target: Path, *args: Any) -> None:
        copies.append(target)
        real_copy(self, target, *args)

    monkeypatch.setattr(write_module.ComicboxArchiveWrite, "_patch_a_copy", spy)
    monkeypatch.setattr(write_module, "TAIL_CAP", 16)

    assert _retag(path).written

    assert copies == [path]
    assert _summary(path) == "New"


def test_a_tags_first_comic_with_a_long_name_takes_a_write(tmp_path: Path) -> None:
    """D11: a name over 241 bytes left no room for the temporary archive's."""
    path = _odd_zip(tmp_path / ("c" * 251 + ".cbz"))
    before = _members(path)

    assert _retag(path).written

    assert _members(path) == before
    assert _summary(path) == "New"
    assert _leftovers(tmp_path) == set()


# ------------------------------------------------- E3: what the copy keeps


def _messages(run: Callable[[], Any]) -> tuple[Any, list[str]]:
    from loguru import logger

    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        return run(), messages
    finally:
        logger.remove(handler)


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions"
)
def test_a_directory_that_cannot_take_the_copy_gets_the_in_place_write(
    tmp_path: Path,
) -> None:
    """E3: it failed with PermissionError; f7357cb wrote it in place."""
    directory = tmp_path / "ro"
    directory.mkdir()
    path = _odd_zip(directory / "odd.cbz")
    mode = directory.stat().st_mode
    directory.chmod(0o555)
    try:
        result, warnings = _messages(lambda: _retag(path, "In Place"))
    finally:
        directory.chmod(mode)

    assert result.written, result.error
    assert _summary(path) == "In Place"
    assert any("unprotected" in message for message in warnings)
    assert _leftovers(directory) == set()


def test_a_leftover_copy_is_removed_by_a_tail_write(tmp_path: Path) -> None:
    """E3: a killed copy's full-size temporary archive stayed for good."""
    path = tmp_path / "comic.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("page-0.jpg", os.urandom(1000))
    assert _retag(path, "First").written
    leftover = write_module.tmp_archive_path(path)
    leftover.write_bytes(os.urandom(5000))

    assert _retag(path).written

    assert not leftover.exists()


@pytest.mark.skipif(not hasattr(os, "listxattr"), reason="no os.listxattr")
def test_the_copy_keeps_extended_attributes(tmp_path: Path) -> None:
    """E3: a user attribute was dropped with the old file."""
    path = _odd_zip(tmp_path / "odd.cbz")
    try:
        os.setxattr(path, "user.comicbox.test", b"kept")  # ty: ignore[missing-attribute]
    except OSError:
        pytest.skip("this filesystem takes no extended attributes")

    assert _retag(path).written

    assert os.getxattr(path, "user.comicbox.test") == b"kept"  # ty: ignore[missing-attribute]


def test_extended_attributes_are_kept_through_os_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E9: on macOS E3 called copyfile(3) through ctypes; only os is used now."""
    attributes: dict[str, dict[str, bytes]] = {}

    def _key(path: Any) -> str:
        return Path(path).name

    def _set(path: Any, name: str, value: bytes) -> None:
        attributes.setdefault(_key(path), {})[name] = value

    monkeypatch.setattr(
        os,
        "listxattr",
        lambda path: list(attributes.get(_key(path), {})),
        raising=False,
    )
    monkeypatch.setattr(
        os, "getxattr", lambda path, name: attributes[_key(path)][name], raising=False
    )
    monkeypatch.setattr(os, "setxattr", _set, raising=False)
    path = _odd_zip(tmp_path / "odd.cbz")
    _set(path, "user.comicbox.test", b"kept")

    assert _retag(path).written

    copies = [name for name in attributes if name != path.name]
    assert copies == [write_module.tmp_archive_path(path).name]
    assert attributes[copies[0]] == {"user.comicbox.test": b"kept"}


def test_the_copy_keeps_the_group(tmp_path: Path) -> None:
    """E3: the new file took its directory's group, not the comic's."""
    path = _odd_zip(tmp_path / "odd.cbz")
    others = [gid for gid in os.getgroups() if gid != path.stat().st_gid]
    if not others:
        pytest.skip("this user belongs to one group only")
    os.chown(path, -1, others[0])

    assert _retag(path).written

    assert path.stat().st_gid == others[0]
