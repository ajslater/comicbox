"""Test decimal parsing."""
from comicbox.metadata.comic_base import ComicBaseMetadata

FIVE = 5.0
FIVE_HALF = 5.5


def test_parse_decimal_int():
    """Test int."""
    assert ComicBaseMetadata.parse_decimal(5) == FIVE


def test_parse_decimal_float():
    """Test float."""
    assert ComicBaseMetadata.parse_decimal(FIVE) == FIVE


def test_parse_decimal_str():
    """Test str."""
    assert ComicBaseMetadata.parse_decimal("5.0") == FIVE
    assert ComicBaseMetadata.parse_decimal("5") == FIVE


def test_parse_decimal_str_half():
    """Test str with halves."""
    assert ComicBaseMetadata.parse_decimal("5½") == FIVE_HALF
    assert ComicBaseMetadata.parse_decimal("5 1/2") == FIVE_HALF


def test_parse_decimal_regex():
    """Test str with suffixes."""
    assert ComicBaseMetadata.parse_decimal("5AU") == FIVE
    assert ComicBaseMetadata.parse_decimal("  5.0AU") == FIVE
    assert ComicBaseMetadata.parse_decimal("MARVEL 5.0AU") == FIVE
