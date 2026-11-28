"""
`-X -d FILE` never overwrites a comic, nor writes two covers to one file.

A comic is what comicbox opens as one, by its bytes; either refusal fails
that comic's file (one line, exit 1).

A file destination took the cover whatever it was: a mistyped `-d`
naming a comic replaced that comic with a JPEG and the run exited 0, and
with several input comics every cover landed on the one file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from tests.const import CIX_CBZ_SOURCE_PATH, PDF_SOURCE_PATH
from tests.util.comics import make_comic

if TYPE_CHECKING:
    from collections.abc import Iterator

_JPEG_MAGIC = b"\xff\xd8\xff"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run_cli(*argv: str) -> tuple[int, str]:
    old_stdout = sys.stdout
    buf = StringIO()
    code = 0
    try:
        sys.stdout = buf
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.stdout = old_stdout
    return code, buf.getvalue()


def _two_comics(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a.cbz"
    b = tmp_path / "b.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, a)
    shutil.copy(CIX_CBZ_SOURCE_PATH, b)
    return a, b


def test_a_comic_destination_is_refused(tmp_path: Path) -> None:
    """The regression: `-X -d a.cbz b.cbz` left a.cbz a JPEG."""
    a, b = _two_comics(tmp_path)
    before = a.read_bytes()
    code, out = _run_cli("-X", "-d", str(a), str(b))
    assert a.read_bytes() == before
    assert code == 1
    assert "1 file(s) failed." in out


def test_a_comic_destination_is_refused_by_content(tmp_path: Path) -> None:
    """A PDF named like an image is still a comic."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    shutil.copy(PDF_SOURCE_PATH, dest)
    before = dest.read_bytes()
    code, _ = _run_cli("-X", "-d", str(dest), str(b))
    assert dest.read_bytes() == before
    assert code == 1


def test_a_comic_cannot_take_its_own_cover(tmp_path: Path) -> None:
    a, _ = _two_comics(tmp_path)
    before = a.read_bytes()
    code, _ = _run_cli("-X", "-d", str(a), str(a))
    assert a.read_bytes() == before
    assert code == 1


def _cover(comic: Path, tmp_path: Path) -> bytes:
    """Extract a comic's cover on its own and return what `-X` saves."""
    out = tmp_path / f"{comic.stem}-cover"
    out.mkdir()
    code, _ = _run_cli("-X", "-d", str(out), str(comic))
    assert code == 0
    (cover,) = out.iterdir()
    return cover.read_bytes()


def _cover_name(comic: Path, tmp_path: Path) -> str:
    """Get the file name `-X` gives a comic's cover in a directory."""
    out = tmp_path / f"{comic.stem}-name"
    out.mkdir()
    code, _ = _run_cli("-X", "-d", str(out), str(comic))
    assert code == 0
    (cover,) = out.iterdir()
    return cover.name


def _two_different_comics(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, a)
    b = make_comic(tmp_path / "b.cbz", series="Other", number="1")
    return a, b


def test_a_second_cover_to_one_file_fails_its_comic(tmp_path: Path) -> None:
    """The first comic's cover is written; the second is refused, not written."""
    a, b = _two_different_comics(tmp_path)
    a_cover = _cover(a, tmp_path)
    dest = tmp_path / "cover.jpg"
    code, out = _run_cli("-X", "-d", str(dest), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    assert dest.read_bytes() == a_cover


def test_a_second_cover_to_one_file_fails_under_jobs(tmp_path: Path) -> None:
    """Workers race for the file: one cover wins, the other comic fails."""
    a, b = _two_different_comics(tmp_path)
    covers = {_cover(a, tmp_path), _cover(b, tmp_path)}
    dest = tmp_path / "cover.jpg"
    code, out = _run_cli("-j", "2", "-X", "-d", str(dest), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    assert dest.read_bytes() in covers


def test_a_directory_of_two_comics_to_one_file(tmp_path: Path) -> None:
    comics = tmp_path / "comics"
    comics.mkdir()
    _two_different_comics(comics)
    dest = tmp_path / "cover.jpg"
    code, out = _run_cli("-r", "-X", "-d", str(dest), str(comics))
    assert code == 1
    assert "1 file(s) failed." in out
    assert dest.exists()


def test_a_comic_suffix_on_a_file_that_is_no_archive_is_overwritten(
    tmp_path: Path,
) -> None:
    """Not a comic by comicbox's own sniff, so it is no comic to protect."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "junk.cbz"
    dest.write_bytes(b"not an archive")
    code, _ = _run_cli("-X", "-d", str(dest), str(b))
    assert code == 0
    assert dest.read_bytes().startswith(_JPEG_MAGIC)


#: Takes pdffile away before comicbox is imported, as a missing extra would,
#: so the test holds however comicbox stores the flag. Exits 3 if PDF
#: support survived, which would test the wrong path.
_WITHOUT_PDFFILE = """
import sys
sys.modules["pdffile"] = None
from comicbox.box import Comicbox
if Comicbox.is_pdf_supported():
    sys.exit(3)
from comicbox import cli
cli.main(["comicbox", *sys.argv[1:]])
"""


def test_a_pdf_is_refused_without_pdf_support(tmp_path: Path) -> None:
    """Without the pdf extra comicbox cannot open a PDF, but never overwrites one."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    shutil.copy(PDF_SOURCE_PATH, dest)
    before = dest.read_bytes()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    offline = "http://127.0.0.1:9"
    env = {
        **os.environ,
        "COMICBOXDIR": str(config_dir),
        "COMICBOX_ONLINE__CACHE__DIR": str(tmp_path / "cache"),
        "HTTPS_PROXY": offline,
        "HTTP_PROXY": offline,
        "ALL_PROXY": offline,
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _WITHOUT_PDFFILE, "-X", "-d", str(dest), str(b)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "is a comic or PDF" in result.stdout
    assert dest.read_bytes() == before


def test_an_existing_image_destination_is_still_overwritten(tmp_path: Path) -> None:
    """A re-run refreshes cover.jpg: pinned, current behavior."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    dest.write_bytes(b"old cover")
    code, _ = _run_cli("-X", "-d", str(dest), str(b))
    assert code == 0
    assert dest.read_bytes().startswith(_JPEG_MAGIC)


def _same_cover_name(tmp_path: Path) -> tuple[Path, Path]:
    """Two comics whose covers share a file name but not their bytes."""
    a = tmp_path / "a.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, a)
    b = tmp_path / "b.cbz"
    with zipfile.ZipFile(a) as src, zipfile.ZipFile(b, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.lower().endswith(".jpg"):
                data += b"b"
            dst.writestr(info, data)
    return a, b


def _out_dir(tmp_path: Path) -> Path:
    out_dir = tmp_path / "covers"
    out_dir.mkdir()
    return out_dir


def test_a_second_cover_of_one_name_in_a_directory_fails_its_comic(
    tmp_path: Path,
) -> None:
    """The first comic's cover keeps the name; the next one fails, not overwrites."""
    a, b = _same_cover_name(tmp_path)
    a_cover = _cover(a, tmp_path)
    out_dir = _out_dir(tmp_path)
    code, out = _run_cli("-X", "-d", str(out_dir), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    (cover,) = out_dir.iterdir()
    assert cover.read_bytes() == a_cover


def test_a_second_cover_of_one_name_in_a_directory_fails_under_jobs(
    tmp_path: Path,
) -> None:
    """Workers race for the name: one cover wins, the other comic fails."""
    a, b = _same_cover_name(tmp_path)
    covers = {_cover(a, tmp_path), _cover(b, tmp_path)}
    out_dir = _out_dir(tmp_path)
    code, out = _run_cli("-j", "2", "-X", "-d", str(out_dir), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    (cover,) = out_dir.iterdir()
    assert cover.read_bytes() in covers


def test_covers_of_different_names_in_a_directory_both_work(tmp_path: Path) -> None:
    a, b = _two_different_comics(tmp_path)
    out_dir = _out_dir(tmp_path)
    code, _ = _run_cli("-X", "-d", str(out_dir), str(a), str(b))
    assert code == 0
    assert len(list(out_dir.iterdir())) == 2


def test_an_archive_at_the_cover_path_in_a_directory_is_refused(
    tmp_path: Path,
) -> None:
    a, _ = _same_cover_name(tmp_path)
    out_dir = _out_dir(tmp_path)
    name = Path(_cover_name(a, tmp_path)).name
    archive = out_dir / name
    shutil.copy(CIX_CBZ_SOURCE_PATH, archive)
    before = archive.read_bytes()
    code, _ = _run_cli("-X", "-d", str(out_dir), str(a))
    assert code == 1
    assert archive.read_bytes() == before


def test_an_earlier_runs_cover_in_a_directory_is_replaced(tmp_path: Path) -> None:
    a, _ = _same_cover_name(tmp_path)
    a_cover = _cover(a, tmp_path)
    out_dir = _out_dir(tmp_path)
    old = out_dir / _cover_name(a, tmp_path)
    old.write_bytes(b"old cover")
    code, _ = _run_cli("-X", "-d", str(out_dir), str(a))
    assert code == 0
    assert old.read_bytes() == a_cover


def test_a_failed_cover_write_in_a_directory_frees_the_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = _same_cover_name(tmp_path)
    b_cover = _cover(b, tmp_path)
    out_dir = _out_dir(tmp_path)
    real_write = Path.write_bytes
    calls: list[Path] = []

    def _first_fails(self: Path, data: bytes) -> int:
        calls.append(self)
        if len(calls) == 1:
            reason = f"No space left on device: {self}"
            raise OSError(28, reason)
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", _first_fails)
    code, out = _run_cli("-X", "-d", str(out_dir), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    (cover,) = out_dir.iterdir()
    assert cover.read_bytes() == b_cover


def test_pages_of_two_comics_into_one_directory_are_unchanged(tmp_path: Path) -> None:
    """Not covers: -x of two comics into one directory still overwrites, exit 0."""
    a, b = _same_cover_name(tmp_path)
    out_dir = _out_dir(tmp_path)
    code, _ = _run_cli("-x", "0:1", "-d", str(out_dir), str(a), str(b))
    assert code == 0
    assert len(list(out_dir.iterdir())) == 2


def test_a_failed_cover_write_leaves_the_file_to_the_next_comic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing went to the file, so the next comic's cover may."""
    a, b = _two_different_comics(tmp_path)
    b_cover = _cover(b, tmp_path)
    dest = tmp_path / "cover.jpg"
    real_write = Path.write_bytes
    calls: list[Path] = []

    def _first_fails(self: Path, data: bytes) -> int:
        calls.append(self)
        if len(calls) == 1:
            reason = f"No space left on device: {self}"
            raise OSError(28, reason)
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", _first_fails)
    code, out = _run_cli("-X", "-d", str(dest), str(a), str(b))
    assert code == 1
    assert "1 file(s) failed." in out
    assert dest.read_bytes() == b_cover
