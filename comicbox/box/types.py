"""Comicbox Types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tarfile import TarFile

    from pdffile import PDFFile
    from py7zr import SevenZipFile
    from rarfile import RarFile
    from zipremove import ZipFile

    ArchiveType = ZipFile | RarFile | TarFile | SevenZipFile | PDFFile
else:
    # ArchiveType is only consumed as a type annotation (every consumer uses
    # `from __future__ import annotations`), so we keep the value resolvable
    # at runtime without pulling in py7zr / rarfile at module-load time.
    ArchiveType = Any
