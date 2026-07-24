"""The --pdf-pages help must match the values the option accepts."""

from __future__ import annotations

from comicbox._pdf import PAGE_FORMAT_PDF, PAGE_FORMAT_VALUES
from comicbox.cli.epilog import (
    _PDF_PAGE_FORMAT_DESC,
    _get_pdf_page_format_phases_table,
)


def test_every_page_format_is_documented() -> None:
    """
    Every value argparse accepts has a help description.

    The values come from the installed pdffile's PageFormat enum. When
    pdffile adds one, the help table gains an undocumented row until a
    description is written for it here.
    """
    for value in PAGE_FORMAT_VALUES:
        assert _PDF_PAGE_FORMAT_DESC.get(value), (
            f"--pdf-pages accepts {value!r} but the help table does not describe it"
        )


def test_help_table_rows_match_accepted_values() -> None:
    """The table documents the accepted values and nothing else."""
    table = _get_pdf_page_format_phases_table()

    assert table.row_count == len(PAGE_FORMAT_VALUES)


def test_pdf_page_format_is_a_valid_value() -> None:
    """The format that merges extracted ranges is one pdffile serves."""
    assert PAGE_FORMAT_PDF in PAGE_FORMAT_VALUES
