#!/usr/bin/env python3
"""
Regenerate the per-page PDF fixtures used by the test suite.

Each ``tests/files/pdf/{N}.pdf`` is the expected single-page-PDF byte output
of ``Comicbox.get_page_by_index(N)`` against ``tests/files/test_pdf.pdf``.
When pymupdf updates or pdffile changes its page-extraction method, those
bytes drift and the PDF page tests fail. Run this script to refresh the
fixtures so they match the current implementation.
"""

from __future__ import annotations

from pathlib import Path

from comicbox.box import Comicbox

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PDF = REPO_ROOT / "tests" / "files" / "test_pdf.pdf"
DEST_DIR = REPO_ROOT / "tests" / "files" / "pdf"


def main() -> None:
    """Regenerate every per-page fixture from the source PDF."""
    if not SOURCE_PDF.is_file():
        reason = f"Source PDF not found: {SOURCE_PDF}"
        raise FileNotFoundError(reason)

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    with Comicbox(SOURCE_PDF) as car:
        page_count = car.get_page_count()
        for index in range(page_count):
            page_bytes = car.get_page_by_index(index)
            if page_bytes is None:
                reason = f"No page bytes returned for index {index}"
                raise RuntimeError(reason)
            out_path = DEST_DIR / f"{index}.pdf"
            out_path.write_bytes(page_bytes)
            print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(page_bytes)} bytes)")  # noqa: T201


if __name__ == "__main__":
    main()
