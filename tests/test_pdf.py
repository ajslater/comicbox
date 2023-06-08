"""Test CBI module."""
from argparse import Namespace
from pathlib import Path

from .test_metadata import TEST_FILES_PATH, TMP_ROOT, read_metadata, write_metadata_pdf

FN = Path("test_pdf.pdf")
ARCHIVE_PATH = TEST_FILES_PATH / FN
TMP_PATH = TMP_ROOT / "test_"
NEW_TEST_PATH = TMP_PATH / FN.with_suffix(".pdf")
METADATA = {
    "scan_info": "Writer",
    "creators": [
        {"person": "Evangelos Vlachogiannis", "role": "writer"},
    ],
    "tags": ["d,e,f"],
    "page_count": 1,
    "ext": "pdf",
    "series": "test pdf",
    "cover_image": "0",
}
CONFIG = Namespace(comicbox=Namespace(write_pdf=True))


def test_read_pdf():
    """Read PDF archive."""
    read_metadata(ARCHIVE_PATH, METADATA)


def test_write_pdf():
    """Write PDF metadata."""
    write_metadata_pdf(TMP_PATH, NEW_TEST_PATH, METADATA, CONFIG)
