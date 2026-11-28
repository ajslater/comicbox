"""
PDF format package (MuPDF + PDF XML).

PDF and PDF_XML share schema + transform code, conditioned on the
optional `pdffile` extra being installed (`PDF_INSTALLED`, so registering
them imports no pymupdf; whether PDFs open is `PDF_ENABLED`). Two separate
FormatRegistrations since MetadataFormats treats them as distinct enum
entries.
"""

from types import MappingProxyType

from comicbox._pdf import PDF_INSTALLED
from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.pdf.transform import MuPDFTransform, PDFXmlTransform

PDF_REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "MuPDF",
        frozenset({"pdf", "mupdf"}),
        "mupdf.json",
        MuPDFTransform,
        lexer="json",
        enabled=PDF_INSTALLED,
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 5,
            "ARCHIVE_PDF": 0,
            "CLI": 4,
            "API": 7,
        }
    ),
    has_tags_without_ids=True,
)

PDF_XML_REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "PDF XML",
        frozenset({"pdfxml"}),
        "pdf.xml",
        PDFXmlTransform,
        lexer="xml",
        enabled=PDF_INSTALLED,
    ),
    sources=MappingProxyType(
        {
            "API": 8,
        }
    ),
    has_tags_without_ids=True,
)
