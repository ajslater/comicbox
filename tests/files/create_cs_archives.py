#!/usr/bin/env python3
"""
Rebuild the Captain Science test comic archives from the source pages.

The page JPEGs in ``Captain Science 001/`` are downsized to small thumbnails and
every Captain Science archive variant is repackaged from a single set of source
files. This keeps the binary test fixtures tiny while preserving each variant's
metadata format (ComicInfo / CoMet / ComicBookInfo / MetronInfo) and container
(zip / 7z / rar / tar).

Run from anywhere: ``python tests/files/create_cs_archives.py``.
Requires the ``7zz`` and ``rar`` binaries on PATH for the .cb7 and .cbr variants.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
SRC = HERE / "Captain Science 001"
STEM = "Captain Science #001"
ARC = SRC.name  # nested archive directory: "Captain Science 001"

THUMB_SIZE = 160
JPEG_QUALITY = 30

CIX = SRC / "comicinfo.xml"  # comicbox-normalized (nested)
CIX_RAW = SRC / "comicinfo-original.xml"  # raw ComicRack style (top-level, PageCount=0)
METRON = SRC / "metroninfo.xml"  # nested in the multi-format archives
METRON_FULL = SRC / "metroninfo-full.xml"  # richer, for the dedicated metron archive
COMET = SRC / "CoMet.xml"
CBI = SRC / "comic-book-info.json"  # ComicBookInfo: stored as the archive comment

# Fixed entry timestamp so rebuilt fixtures are reproducible and the metadata
# mtime is stable (see tests/test_mtime.py).
FIXED_DT = (2026, 5, 17, 21, 43, 38)


def downsize_pages() -> None:
    """Shrink the source page JPEGs to thumbnails in place (idempotent)."""
    for page in sorted(SRC.glob("CaptainScience#1_*.jpg")):
        with Image.open(page) as im:
            if max(im.size) <= THUMB_SIZE:
                continue
            im.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="jpeg", quality=JPEG_QUALITY)
        page.write_bytes(buf.getvalue())


def _nested_pages() -> list[tuple[Path, str]]:
    """Source pages mapped into the nested archive directory."""
    return [(p, f"{ARC}/{p.name}") for p in sorted(SRC.glob("CaptainScience#1_*.jpg"))]


def _stage(root: Path, members: list[tuple[Path, str]]) -> None:
    """Copy members into a staging dir by arcname (for the CLI archivers)."""
    for src, arc in members:
        dst = root / arc
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_zip(
    name: str, members: list[tuple[Path, str]], comment: Path | None = None
) -> None:
    out = HERE / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, arc in members:
            info = zipfile.ZipInfo(arc, date_time=FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, src.read_bytes())
        if comment is not None:
            zf.comment = comment.read_bytes()


def write_tar(name: str, members: list[tuple[Path, str]]) -> None:
    out = HERE / name
    with tarfile.open(out, "w:xz") as tf:
        for src, arc in members:
            tf.add(src, arcname=arc)


def write_7z(name: str, members: list[tuple[Path, str]]) -> None:
    out = (HERE / name).resolve()
    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as td:
        _stage(Path(td), members)
        arcs = [arc for _, arc in members]
        subprocess.run(
            ["7zz", "a", "-mx=9", "-bso0", "-bsp0", str(out), *arcs],
            cwd=td,
            check=True,
        )


def write_rar(
    name: str, members: list[tuple[Path, str]], comment: Path | None = None
) -> None:
    out = (HERE / name).resolve()
    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as td:
        _stage(Path(td), members)
        arcs = [arc for _, arc in members]
        cmd = ["rar", "a", "-m5", "-idq"]
        if comment is not None:
            cmd.append(f"-z{comment.resolve()}")
        subprocess.run([*cmd, str(out), *arcs], cwd=td, check=True)


def build_all() -> None:
    pages = _nested_pages()

    # zip containers
    write_zip(
        f"{STEM}.cbz",
        [
            *pages,
            (CIX, f"{ARC}/comicinfo.xml"),
            (METRON, f"{ARC}/metroninfo.xml"),
            (CIX_RAW, "comicinfo.xml"),
        ],
    )
    write_zip(
        f"{STEM}-cix.cbz",
        [*pages, (CIX, f"{ARC}/comicinfo.xml"), (CIX_RAW, "comicinfo.xml")],
    )
    write_zip(f"{STEM}-comet.cbz", [*pages, (COMET, f"{ARC}/CoMet.xml")])
    write_zip(f"{STEM}-metron.cbz", [(METRON_FULL, "metroninfo.xml")])

    # rar containers (ComicBookInfo lives in the archive comment)
    write_rar(f"{STEM}-cbi.cbr", pages, comment=CBI)
    write_rar(f"{STEM}-cix-cbi.cbr", [*pages, (CIX_RAW, "comicinfo.xml")], comment=CBI)

    # 7z and tar containers
    write_7z(
        f"{STEM}.cb7",
        [*pages, (CIX, f"{ARC}/comicinfo.xml"), (METRON, f"{ARC}/metroninfo.xml")],
    )
    write_tar(
        f"{STEM}-cix.cbt",
        [*pages, (METRON, f"{ARC}/metroninfo.xml"), (CIX, f"{ARC}/comicinfo.xml")],
    )


def main() -> None:
    downsize_pages()
    build_all()
    for archive in sorted(HERE.glob(f"{STEM}*")):
        if archive.is_file() and archive.suffix in {".cbz", ".cbr", ".cb7", ".cbt"}:
            print(f"{archive.stat().st_size:>8} bytes  {archive.name}")


if __name__ == "__main__":
    main()
