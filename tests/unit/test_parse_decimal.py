"""Test decimal parsing."""

from decimal import Decimal

import pytest
from marshmallow import ValidationError

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.number_fields import DecimalField, IntegerField

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


@pytest.mark.parametrize("value", ["2,99", "1,234", "1,234,567", "1.234,56"])
def test_parse_decimal_separator_not_truncated(value: str) -> None:
    """A decimal comma or thousands separator is rejected, not cut short."""
    assert DecimalField.parse_str(value) is None
    with pytest.raises(ValidationError):
        DecimalField().deserialize(value)


def test_parse_decimal_liberal_reads_unchanged() -> None:
    """Suffixes, padding and half glyphs still read."""
    df = DecimalField()
    assert df.deserialize("1.5") == Decimal("1.5")
    assert df.deserialize(" 1.50 ") == Decimal("1.50")
    assert df.deserialize("½") == Decimal("0.5")
    assert df.deserialize("5 1/2") == FIVE_HALF
    assert df.deserialize("v2") == Decimal(2)


@pytest.mark.parametrize("value", ["2,99", "1,234", "1,234,567"])
def test_parse_integer_separator_not_truncated(value: str) -> None:
    """A decimal comma or thousands separator is rejected, not cut short."""
    assert IntegerField.parse_str(value) is None
    with pytest.raises(ValidationError):
        IntegerField().deserialize(value)


def test_parse_integer_first_number_unchanged() -> None:
    """Liberal integer reads still take the first number."""
    field = IntegerField()
    assert field.deserialize("v2") == 2
    assert field.deserialize("1-3") == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4.5/5", Decimal("4.5")),
        ("3/4", Decimal(3)),
        ("1/2", Decimal("0.5")),
        ("5 1/2", Decimal("5.5")),
    ],
)
def test_parse_decimal_reads_number_before_slash(value: str, expected: Decimal) -> None:
    """The number before a slash is read; a half is still 0.5."""
    assert DecimalField().deserialize(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1999/2000", 1999), ("06/2020", 6), ("12/24", 12), ("3/4", 3), ("1/2", 1)],
)
def test_parse_integer_reads_number_before_slash(value: str, expected: int) -> None:
    """The number before a slash is read."""
    assert IntegerField().deserialize(value) == expected


def test_comic_info_reads_number_before_slash() -> None:
    """ComicInfo rating, year, volume, month and count read the leading number."""
    xml = (
        "<ComicInfo><Series>Foo</Series>"
        "<CommunityRating>4.5/5</CommunityRating><Year>1999/2000</Year>"
        "<Volume>2019/2020</Volume><Month>06/2020</Month><Count>12/24</Count>"
        "</ComicInfo>"
    )
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        md = car.to_dict()["comicbox"]
    assert md["community_rating"]["average_rating"] == Decimal("4.5")
    assert md["date"]["year"] == 1999
    assert md["date"]["month"] == 6
    assert md["volume"]["number"] == 2019
    assert md["volume"]["issue_count"] == 12


def test_comet_volume_reads_number_before_slash() -> None:
    """A CoMet volume such as 2019/20 reads as 2019."""
    xml = "<comet><title>T</title><volume>2019/20</volume></comet>"
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMET)
        md = car.to_dict()["comicbox"]
    assert md["volume"]["number"] == 2019


def test_separator_value_is_dropped() -> None:
    """The schema drops, and logs, a value it cannot read instead of a wrong one."""
    xml = "<ComicInfo><Series>Foo</Series><CommunityRating>2,99</CommunityRating></ComicInfo>"
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        md = car.to_dict()["comicbox"]
    assert "community_rating" not in md
