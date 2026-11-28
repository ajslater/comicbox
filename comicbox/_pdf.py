"""
Optional comicbox-pdffile integration.

Single source of truth for whether the optional ``pdffile`` package is
installed and importable. Importing it loads pymupdf, about half a second,
so nothing here imports it until something asks: ``PDF_ENABLED`` and
``PDFFile`` are looked up lazily, by ``get_pdffile()``. When pdffile does
not import, ``PDFFile`` is ``None`` at runtime; call sites must guard with
``PDF_ENABLED`` before touching it. For the type checker, import
``PDFFile`` from ``pdffile`` directly under ``TYPE_CHECKING``.
"""

from __future__ import annotations

import sys
from functools import cache
from importlib.util import find_spec
from threading import Lock
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from pdffile import PDFFile

__all__ = (
    "PAGE_FORMAT_IMAGE",
    "PAGE_FORMAT_PDF",
    "PAGE_FORMAT_PIXMAP_JPEG",
    "PAGE_FORMAT_VALUES",
    "PDF_ENABLED",
    "PDF_INSTALLED",
    "PDFFile",
    "get_pdffile",
    "is_pdffile",
    "pdf_enabled",
)

#: The page format that yields pdf pages. Also pdffile's own default.
PAGE_FORMAT_PDF: str = "pdf"

#: The page format that extracts a page's first image as stored.
PAGE_FORMAT_IMAGE: str = "image"

#: The page format that rasterizes the whole page to an RGB jpeg.
PAGE_FORMAT_PIXMAP_JPEG: str = "pixmap_jpeg"


def _is_installed() -> bool:
    try:
        return find_spec("pdffile") is not None
    except ValueError:
        # A module in sys.modules without a spec, as a test stub is, is there.
        return True


#: Whether pdffile is installed, not whether it imports. Only for what is
#: decided at import or on every run without paying for pymupdf: the PDF
#: formats' registration, the CLI options and the config choices. Whether
#: a PDF opens, and ``is_pdf_supported()``, ask ``PDF_ENABLED``.
PDF_INSTALLED: bool = _is_installed()

#: pdffile.PageFormat's values, written out so that naming them costs no
#: import. A test holds them to pdffile's.
PAGE_FORMAT_VALUES: tuple[str, ...] = (
    (
        PAGE_FORMAT_PDF,
        PAGE_FORMAT_IMAGE,
        "pixmap",
        "image_if_dominant",
        PAGE_FORMAT_PIXMAP_JPEG,
    )
    if PDF_INSTALLED
    else ()
)


_IMPORT_LOCK = Lock()


@cache
def get_pdffile() -> type[PDFFile] | None:
    """Import pdffile once, on first use. None when it does not import."""
    # Threads asking at once all miss this cache. The lock and the inner
    # cache let the first one import, and warn; a failed import is not
    # kept in sys.modules, so each would otherwise try again and warn again.
    with _IMPORT_LOCK:
        return _import_pdffile()


@cache
def _import_pdffile() -> type[PDFFile] | None:
    try:
        # PageFormat too: comicbox's page formats need a pdffile that has it.
        from pdffile import PageFormat, PDFFile  # noqa: F401 # pyright: ignore[reportUnusedImport]
    except Exception as exc:
        # An optional extra must never take the rest of comicbox down with
        # it, and importing it can fail with more than ImportError: pymupdf
        # asserts at import that its libmupdf is the version it was built
        # against. Absent is the expected case and stays quiet; installed
        # but broken is said out loud, or PDFs silently stop being comics.
        if not (isinstance(exc, ModuleNotFoundError) and exc.name == "pdffile"):
            from loguru import logger

            logger.warning(f"PDF support disabled: pdffile failed to import: {exc!r}")
        return None
    return PDFFile


def pdf_enabled() -> bool:
    """Whether pdffile imports. The first call imports it."""
    return get_pdffile() is not None


def is_pdffile(archive: object) -> TypeGuard[PDFFile]:
    """
    Whether an open archive is a PDFFile, without importing pdffile to ask.

    A PDFFile can only exist once pdffile is imported.
    """
    module = sys.modules.get("pdffile")
    pdffile_cls = getattr(module, "PDFFile", None) if module else None
    return pdffile_cls is not None and isinstance(archive, pdffile_cls)


if TYPE_CHECKING:
    PDF_ENABLED: bool
else:

    def __getattr__(name: str) -> Any:
        """Answer the PDF_ENABLED and PDFFile names on first lookup."""
        if name == "PDF_ENABLED":
            return pdf_enabled()
        if name == "PDFFile":
            return get_pdffile()
        reason = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(reason)
