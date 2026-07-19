"""
ComicBookInfo rating <-> canonical community_rating.average_rating conversion.

ComicBookInfo's ``rating`` field is an integer with no spec-defined scale.
Different apps wrote it on different scales (0-10 was common, but 0-100
appeared in the wild too). The canonical comicbox
``community_rating.average_rating`` follows ComicInfo's ``CommunityRating``
spec: ``0.0`` to ``5.0`` with one decimal place of meaningful precision.

This module bridges the two with a magnitude-based heuristic:

    * ``value <= 10``  -> divisor 2     (assume 0-10 scale)
    * ``11..100``      -> divisor 20    (assume 0-100 scale)
    * ``101..1000``    -> divisor 200   (assume 0-1000 scale)
    * ...and so on, generalized as ``2 * 10^(ceil(log10(value)) - 1)``.

Inverse direction (write-back): canonical 0-5 ``Decimal`` -> integer 0-10.
Deliberately lossy: 4.37 round-trips to 9 then re-reads as 4.5. Accepted
trade-off for keeping the on-disk CBI value an integer.
"""

from decimal import ROUND_HALF_UP, Decimal
from math import ceil, log10
from typing import Any

from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.transform import COMMUNITY_RATING_AVERAGE_KEYPATH

_ONE_DP = Decimal("0.1")
_ZERO = Decimal("0.0")
_MAX_CANONICAL = Decimal("5.0")
_CBI_RATING_TAG = "rating"
# Upper bound of the "assume 0-10 input scale" bucket. CBI inputs at or below
# this divide by 2; above, divide by 2 * 10^(ceil(log10(value)) - 1).
_CBI_LOW_BUCKET_MAX = 10
# Canonical 0-5 maps onto CBI's integer 0-10 with a factor of 2.
_CBI_INT_SCALE = Decimal(2)
_CBI_INT_MAX = Decimal(10)


def cbi_rating_to_canonical(value: Any) -> Decimal | None:
    """Convert a CBI integer rating to the canonical 0-5 scale (1 dp)."""
    if value is None:
        return None
    try:
        d = Decimal(value)
    except (ArithmeticError, TypeError, ValueError):
        return None
    if d <= 0:
        return _ZERO
    if d <= _CBI_LOW_BUCKET_MAX:
        divisor = _CBI_INT_SCALE
    else:
        implied_max = Decimal(10) ** ceil(log10(float(d)))
        divisor = implied_max / _MAX_CANONICAL
    result = (d / divisor).quantize(_ONE_DP, rounding=ROUND_HALF_UP)
    return min(result, _MAX_CANONICAL)


def canonical_to_cbi_rating(value: Any) -> int | None:
    """Convert canonical 0-5 average_rating to a CBI 0-10 integer."""
    if value is None:
        return None
    try:
        d = Decimal(value)
    except (ArithmeticError, TypeError, ValueError):
        return None
    scaled = (d * _CBI_INT_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    clamped = max(Decimal(0), min(scaled, _CBI_INT_MAX))
    return int(clamped)


def cbi_rating_to_cb() -> MetaSpec:
    """Spec: CBI ``rating`` integer -> comicbox ``community_rating.average_rating``."""
    return MetaSpec(
        key_map={COMMUNITY_RATING_AVERAGE_KEYPATH: _CBI_RATING_TAG},
        spec=(cbi_rating_to_canonical,),
    )


def cbi_rating_from_cb() -> MetaSpec:
    """Spec: comicbox ``community_rating.average_rating`` -> CBI ``rating`` integer."""
    return MetaSpec(
        key_map={_CBI_RATING_TAG: COMMUNITY_RATING_AVERAGE_KEYPATH},
        spec=(canonical_to_cbi_rating,),
    )
