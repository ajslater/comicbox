"""Get ZipInfo like attributes from all archive info types."""

from __future__ import annotations

from tarfile import TarFile
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from comicbox._pdf import PAGE_FORMAT_IMAGE, PDF_ENABLED
from comicbox.box.archive.sniff import sniff_ext

if TYPE_CHECKING:
    from pdffile import PDFFile
    from py7zr import SevenZipFile
    from py7zr.io import BytesIOFactory
    from rarfile import RarFile
    from zipremove import ZipFile

    from comicbox.box.archive.archiveinfo import InfoType

    ArchiveType = ZipFile | SevenZipFile | RarFile | TarFile | PDFFile
else:
    from comicbox._pdf import PDFFile

    ArchiveType = Any  # avoid pulling in py7zr / rarfile at module-load time


# Dispatch by attribute presence rather than isinstance — keeps the heavy
# py7zr / rarfile imports off the hot read path for CBZ-only workers.
# `reset` is unique to py7zr.SevenZipFile among the archive types we accept.


class Archive:
    """Generic Archive ZipFile like methods."""

    @staticmethod
    def namelist(archive: ArchiveType) -> tuple[str, ...]:
        """Return namelist."""
        return tuple(
            archive.getnames() if isinstance(archive, TarFile) else archive.namelist()
        )

    @staticmethod
    def infolist(archive: ArchiveType) -> tuple[InfoType, ...]:
        """Return infolist."""
        if isinstance(archive, TarFile):
            infolist = archive.getmembers()
        elif hasattr(archive, "reset"):  # SevenZipFile
            infolist = cast("SevenZipFile", archive).list()
        else:
            infolist = cast("ZipFile | RarFile | PDFFile", archive).infolist()
        return tuple(infolist)

    @staticmethod
    def _read_tarfile(archive: TarFile, filename: str) -> bytes:
        file_obj = archive.extractfile(filename)
        return file_obj.read() if file_obj else b""

    @staticmethod
    def _read_7zipfile(
        archive: SevenZipFile, factory: BytesIOFactory | None, filename: str
    ) -> bytes:
        """Read a single file from 7zip."""
        if not factory:
            return b""
        archive.extract(targets=[filename], factory=factory)
        file_obj = factory.products.get(filename)
        data = file_obj.read() if file_obj else b""
        archive.reset()
        return data

    @staticmethod
    def _read_pdffile_rotated_render(
        archive: PDFFile, filename: str
    ) -> tuple[bytes, str] | None:
        """
        Render an ``image`` read when raw bytes would bake in rotation.

        Raw first-image extraction can't carry the page's display
        rotation (/Rotate or a rotated placement), so an ``image`` read
        of a rotated image-dominant page would write the stored,
        wrong-way-up orientation into extracted files and converted
        archives. Detect that case and render the whole page instead.
        Returns None when the stored bytes are fine as-is, the name is
        an embedded file, or detection fails.
        """
        try:
            index = archive.valid_pagenum(filename)
        except ValueError:
            return None  # embedded file, not a page
        try:
            if not archive.classify_page(index).rotation:
                return None
            return archive.read_full_pixmap_jpeg(index)
        except Exception as exc:
            logger.warning(
                f"Rotation detection failed for pdf page {filename}, "
                f"extracting as stored: {exc}"
            )
            return None

    @classmethod
    def _read_pdffile(
        cls, archive: PDFFile, filename: str, pdf_format: str, props: dict | None
    ) -> bytes:
        """Read a pdf page and report the format actually served."""
        if pdf_format == PAGE_FORMAT_IMAGE and (
            served := cls._read_pdffile_rotated_render(archive, filename)
        ):
            data, ext = served
            if props is not None:
                props["ext"] = ext
            return data
        data = archive.read(filename, fmt=pdf_format, props=props)
        # Pdf page names carry no extension of their own, so callers name the
        # extracted file after props["ext"]. A reader that serves a page image
        # instead of a page pdf without saying so would leave image data named
        # ".pdf", so fall back to the data itself.
        if props is not None and not props.get("ext") and (ext := sniff_ext(data)):
            props["ext"] = ext
        return data

    @classmethod
    def read(
        cls,
        archive: ArchiveType,
        filename: str,
        factory: BytesIOFactory | None,
        pdf_format: str = "",
        props: dict | None = None,
    ) -> bytes:
        """Read one file in the archive's data."""
        if PDF_ENABLED and isinstance(archive, PDFFile):
            return cls._read_pdffile(archive, filename, pdf_format, props)
        if isinstance(archive, TarFile):
            return cls._read_tarfile(archive, filename)
        if hasattr(archive, "reset"):  # SevenZipFile
            return cls._read_7zipfile(cast("SevenZipFile", archive), factory, filename)
        return cast("ZipFile | RarFile | PDFFile", archive).read(filename)
