"""Test CLI extract actions."""

from comicbox import cli
from tests.const import (
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    COVER_FN,
)
from tests.util import get_tmp_dir, my_cleanup, my_setup

TMP_DIR = get_tmp_dir(__file__)
TMP_COVER_PATH = TMP_DIR / COVER_FN


def _test_cli_action_extract_util(path, args, test_files):
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


def _test_cli_action_extract_cover(path):
    """Test cli metadata write to file."""
    _test_cli_action_extract_util(path, ["-o"], [TMP_COVER_PATH])


def test_cli_action_extract_cover_cbr():
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CBI_CBR_SOURCE_PATH)


def test_cli_action_extract_cover_cbt():
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CIX_CBT_SOURCE_PATH)


def test_cli_action_extract_cover_cbz():
    """Test cli cover extract."""
    _test_cli_action_extract_cover(CIX_CBZ_SOURCE_PATH)


def _test_cli_action_extract(path, extract, test_files):
    args = ("-e", extract)
    _test_cli_action_extract_util(path, args, test_files)


def test_cli_action_extract_from():
    """Test extract files."""
    test_files = ("CaptainScience#1_03.jpg",)
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "2", test_files)


def test_cli_action_extract_from_forward():
    """Test extract files."""
    test_files = (
        "CaptainScience#1_34.jpg",
        "CaptainScience#1_35.jpg",
        "CaptainScience#1_36.jpg",
    )
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "33:", test_files)


def test_cli_action_extract_to_backward():
    """Test extract files."""
    test_files = (
        "CaptainScience#1_01.jpg",
        "CaptainScience#1_02.jpg",
        "CaptainScience#1_03.jpg",
    )
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, ":2", test_files)


def test_cli_action_extract_from_to():
    """Test extract files."""
    test_files = [
        "CaptainScience#1_17.jpg",
        "CaptainScience#1_18.jpg",
    ]
    _test_cli_action_extract(CIX_CBZ_SOURCE_PATH, "16:17", test_files)
