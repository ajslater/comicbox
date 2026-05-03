"""
Optional comicbox-pdffile integration.

Single source of truth for whether the optional ``pdffile`` package is
installed. When it is absent, ``PDFFile`` is ``None`` at runtime; call
sites must guard with ``if PDF_ENABLED`` before touching it. For the type
checker, import ``PDFFile`` from ``pdffile`` directly under ``TYPE_CHECKING``.
"""

from typing import TYPE_CHECKING

__all__ = ("PAGE_FORMAT_VALUES", "PDF_ENABLED", "PDFFile")

if TYPE_CHECKING:
    from pdffile import PDFFile

    PDF_ENABLED: bool
    PAGE_FORMAT_VALUES: tuple[str, ...]
else:
    try:
        from pdffile import PageFormat, PDFFile

        PDF_ENABLED = True
        PAGE_FORMAT_VALUES = tuple(e.value for e in PageFormat)
    except ImportError:
        PDFFile = None
        PDF_ENABLED = False
        PAGE_FORMAT_VALUES = ()
