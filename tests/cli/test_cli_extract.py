"""Test CLI extract actions."""

from collections.abc import Sequence
from pathlib import Path

from comicbox import cli
from tests.const import (
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    CIX_PDF_SOURCE_PATH,
    COVER_FN,
    PDF_SOURCE_PATH,
)
from tests.util import get_tmp_dir, my_cleanup, my_setup

TMP_DIR = get_tmp_dir(__file__)
TMP_COVER_PATH = TMP_DIR / COVER_FN


def _test_cli_action_extract_util(
    path: Path,
    args: Sequence[str],
    test_files: Sequence[Path | str],
) -> None:
    """Test cli metadata write to file."""
    my_setup(TMP_DIR)

    cli.main(
        (
            "comicbox",
            "-d",
            str(TMP_DIR),
            *args,
            str(path),
        )
    )

    list_dir = list(TMP_DIR.iterdir())
    assert len(list_dir) == len(test_files)
    for tf in test_files:
        full_path = TMP_DIR / tf
        assert full_path.exists()
    my_cleanup(TMP_DIR)


def _test_cli_action_extract_cover(path: Path) -> None:
    """Test cli metadata write to file."""
    _test_cli_action_extract_util(path, ["--extract-covers"], [TMP_COVER_PATH])


def test_cli_action_extract_cover_cbr() -> None:
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CBI_CBR_SOURCE_PATH)


def test_cli_action_extract_cover_cbt() -> None:
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CIX_CBT_SOURCE_PATH)


def test_cli_action_extract_cover_cbz() -> None:
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CIX_CBZ_SOURCE_PATH)


def _test_cli_action_extract(
    path: Path, extract: str, test_files: list[str] | tuple[str, ...]
) -> None:
    args = ("--extract-pages", extract)
    _test_cli_action_extract_util(path, args, test_files)


def test_cli_action_extract_from() -> None:
    """Test extract files."""
    test_files = ("CaptainScience#1_03.jpg",)
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "2", test_files)


def test_cli_action_extract_from_forward() -> None:
    """Test extract files."""
    test_files = (
        "CaptainScience#1_04.jpg",
        "CaptainScience#1_05.jpg",
    )
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "3:", test_files)


def test_cli_action_extract_to_backward() -> None:
    """Test extract files."""
    test_files = (
        "CaptainScience#1_01.jpg",
        "CaptainScience#1_02.jpg",
        "CaptainScience#1_03.jpg",
    )
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, ":2", test_files)


def test_cli_action_extract_from_to() -> None:
    """Test extract files."""
    test_files = [
        "CaptainScience#1_03.jpg",
        "CaptainScience#1_04.jpg",
    ]
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "2:3", test_files)


def _test_cli_action_extract_pdf(
    extract: str, test_files: tuple[str, ...], *pdf_pages: str
) -> None:
    args = ("--extract-pages", extract, *pdf_pages)
    _test_cli_action_extract_util(PDF_SOURCE_PATH, args, test_files)


def test_cli_action_extract_pdf_range() -> None:
    """Test a pdf page range extracts as one pdf."""
    _test_cli_action_extract_pdf("1:3", ("1-3.pdf",), "--pdf-pages", "pdf")


def test_cli_action_extract_pdf_range_forward() -> None:
    """Test an open ended pdf range is named for the pages it holds."""
    _test_cli_action_extract_pdf("2:", ("2-3.pdf",), "--pdf-pages", "pdf")


def test_cli_action_extract_pdf_range_tagged() -> None:
    """Test an open ended range on a pdf with embedded metadata still merges."""
    _test_cli_action_extract_util(
        CIX_PDF_SOURCE_PATH,
        ("--extract-pages", "1:", "--pdf-pages", "pdf"),
        ("1-3.pdf",),
    )


def test_cli_action_extract_pdf_range_backward() -> None:
    """Test an open beginning pdf range is named for the pages it holds."""
    _test_cli_action_extract_pdf(":2", ("0-2.pdf",), "--pdf-pages", "pdf")


def test_cli_action_extract_pdf_range_default_format() -> None:
    """Test pdf pages merge without an explicit --pdf-pages, which defaults to pdf."""
    _test_cli_action_extract_pdf("1:3", ("1-3.pdf",))


def test_cli_action_extract_pdf_single_page() -> None:
    """Test a single pdf page is not renamed as a range."""
    _test_cli_action_extract_pdf("2", ("2.pdf",), "--pdf-pages", "pdf")


def test_cli_action_extract_pdf_pixmap_not_merged() -> None:
    """Test that only the pdf format merges a range."""
    _test_cli_action_extract_pdf(
        "1:3", ("1.ppm", "2.ppm", "3.ppm"), "--pdf-pages", "pixmap"
    )
