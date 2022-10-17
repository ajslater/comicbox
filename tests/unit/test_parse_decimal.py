"""Test decimal parsing."""
from comicbox.metadata.comic_base import ComicBaseMetadata


def test_parse_decimal_int():
    """Test int."""
    assert 5.0 == ComicBaseMetadata.parse_decimal(5)


def test_parse_decimal_float():
    """Test float."""
    assert 5.0 == ComicBaseMetadata.parse_decimal(5.0)


def test_parse_decimal_str():
    """Test str."""
    assert 5.0 == ComicBaseMetadata.parse_decimal("5.0")
    assert 5.0 == ComicBaseMetadata.parse_decimal("5")


def test_parse_decimal_str_half():
    """Test str with halves."""
    assert 5.5 == ComicBaseMetadata.parse_decimal("5½")
    assert 5.5 == ComicBaseMetadata.parse_decimal("5 1/2")


def test_parse_decimal_regex():
    """Test str with suffixes."""
    assert 5.0 == ComicBaseMetadata.parse_decimal("5AU")
    assert 5.0 == ComicBaseMetadata.parse_decimal("  5.0AU")
    assert 5.0 == ComicBaseMetadata.parse_decimal("MARVEL 5.0AU")
