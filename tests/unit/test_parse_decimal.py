"""Test decimal parsing."""

from comicbox.fields.number_fields import DecimalField

FIVE = 5.0
FIVE_HALF = 5.5


def test_parse_decimal_int() -> None:
    """Test int."""
    df = DecimalField()
    assert df.deserialize(5) == FIVE


def test_parse_decimal_float() -> None:
    """Test float."""
    df = DecimalField()
    assert df.deserialize(FIVE) == FIVE


def test_parse_decimal_str() -> None:
    """Test str."""
    df = DecimalField()
    assert df.deserialize("5.0") == FIVE
    assert df.deserialize("5") == FIVE


def test_parse_decimal_str_half() -> None:
    """Test str with halves."""
    df = DecimalField()
    assert df.deserialize("5½") == FIVE_HALF
    assert df.deserialize("5 1/2") == FIVE_HALF


def test_parse_decimal_regex() -> None:
    """Test str with suffixes."""
    df = DecimalField()
    assert df.deserialize("5AU") == FIVE
    assert df.deserialize("  5.0AU") == FIVE
    assert df.deserialize("MARVEL 5.0AU") == FIVE
