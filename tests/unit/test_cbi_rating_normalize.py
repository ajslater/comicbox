"""Tests for ComicBookInfo <-> canonical critical_rating conversion."""

from decimal import Decimal

import pytest

from comicbox.formats.comic_book_info.transform.rating import (
    canonical_to_cbi_rating,
    cbi_rating_to_canonical,
)

# Each tuple: (cbi_input, expected_canonical_decimal)
TO_CANONICAL_PARAMS = (
    # None / non-positive
    (None, None),
    (0, Decimal("0.0")),
    (-3, Decimal("0.0")),
    # 0..10 bucket: divisor 2
    (1, Decimal("0.5")),
    (5, Decimal("2.5")),
    (9, Decimal("4.5")),
    (10, Decimal("5.0")),
    # 11..100 bucket: divisor 20
    (11, Decimal("0.6")),  # 0.55 rounded half-up to 0.6
    (50, Decimal("2.5")),
    (90, Decimal("4.5")),
    (100, Decimal("5.0")),
    # 101..1000 bucket: divisor 200
    (101, Decimal("0.5")),  # 0.505 -> 0.5
    (500, Decimal("2.5")),
    (1000, Decimal("5.0")),
    # 1001..10000 bucket: divisor 2000
    (1001, Decimal("0.5")),
    (5000, Decimal("2.5")),
    (10000, Decimal("5.0")),
    # Decimal inputs work too
    (Decimal("7.5"), Decimal("3.8")),
)


@pytest.mark.parametrize(("value", "expected"), TO_CANONICAL_PARAMS)
def test_cbi_rating_to_canonical(value, expected) -> None:
    """Each magnitude bucket produces a value clamped to [0, 5] at one dp."""
    assert cbi_rating_to_canonical(value) == expected


def test_cbi_rating_to_canonical_invalid() -> None:
    """Non-numeric inputs return None rather than raising."""
    assert cbi_rating_to_canonical("not a number") is None


# Each tuple: (canonical_input, expected_cbi_integer)
FROM_CANONICAL_PARAMS = (
    (None, None),
    (Decimal("0.0"), 0),
    (Decimal("0.5"), 1),
    (Decimal("2.5"), 5),
    (Decimal("4.5"), 9),
    (Decimal("5.0"), 10),
    # Out-of-range clamped both ways
    (Decimal("-1.0"), 0),
    (Decimal("99.0"), 10),
    # Rounding: 4.37 * 2 = 8.74 -> 9
    (Decimal("4.37"), 9),
    # Edge: 4.25 * 2 = 8.50 -> 9 under ROUND_HALF_UP
    (Decimal("4.25"), 9),
)


@pytest.mark.parametrize(("value", "expected"), FROM_CANONICAL_PARAMS)
def test_canonical_to_cbi_rating(value, expected) -> None:
    """Canonical decimals serialize to integer 0..10 with clamping."""
    assert canonical_to_cbi_rating(value) == expected


def test_canonical_to_cbi_rating_invalid() -> None:
    """Non-numeric inputs return None rather than raising."""
    assert canonical_to_cbi_rating("not a number") is None


# Each tuple: (cbi_in, expected_canonical, cbi_out_after_round_trip)
ROUND_TRIP_PARAMS = (
    (0, Decimal("0.0"), 0),
    (2, Decimal("1.0"), 2),
    (4, Decimal("2.0"), 4),
    (8, Decimal("4.0"), 8),
    (10, Decimal("5.0"), 10),
)


@pytest.mark.parametrize(("cbi_in", "canonical", "cbi_out"), ROUND_TRIP_PARAMS)
def test_cbi_rating_round_trip(cbi_in, canonical, cbi_out) -> None:
    """Even integers in the 0-10 range round-trip exactly."""
    intermediate = cbi_rating_to_canonical(cbi_in)
    assert intermediate == canonical
    assert canonical_to_cbi_rating(intermediate) == cbi_out


# CB-5: verify the canonical ComicboxSubSchema clamps out-of-range
# critical_rating to [0, 5] via the RangedNumberMixin (rather than raising)
# and quantizes to one decimal place.
CANONICAL_SCHEMA_CLAMP_PARAMS = (
    # (input value, expected stored value after clamp)
    (Decimal("3.5"), Decimal("3.5")),  # in-range passes through at 1 dp
    (Decimal("0.0"), Decimal("0.0")),
    (Decimal("5.0"), Decimal("5.0")),
    (Decimal("7.0"), Decimal("5.0")),  # CIX-spec-violating value clamps to max
    (Decimal("-2.0"), Decimal("0.0")),  # negative clamps to min
    (Decimal("3.55"), Decimal("3.6")),  # extra precision rounds to 1 dp
)


@pytest.mark.parametrize(("value", "expected"), CANONICAL_SCHEMA_CLAMP_PARAMS)
def test_canonical_schema_clamps_critical_rating(value, expected) -> None:
    """The canonical schema's critical_rating field clamps to [0, 5] at 1 dp."""
    # Mirror the constructor used in
    # comicbox.formats.comicbox.schema.ComicboxSubSchemaMixin.critical_rating
    from comicbox.formats.base.fields.number_fields import DecimalField

    field = DecimalField(places=1, minimum=Decimal(0), maximum=Decimal(5))
    assert field.deserialize(value) == expected
