"""MetronInfo CommunityRating Transform."""

from typing import Any

from comicbox.empty import is_empty
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import (
    AVERAGE_RATING_KEY,
    COMMUNITY_RATING_KEY,
    RATING_COUNT_KEY,
)
from comicbox.formats.comicbox.transform import (
    COMMUNITY_RATING_AVERAGE_KEYPATH,
    COMMUNITY_RATING_COUNT_KEYPATH,
)
from comicbox.formats.metron_info.schema import COMMUNITY_RATING_TAG

AVERAGE_RATING_TAG = "AverageRating"
RATING_COUNT_TAG = "RatingCount"
AVERAGE_RATING_TAGPATH = f"{COMMUNITY_RATING_TAG}.{AVERAGE_RATING_TAG}"
RATING_COUNT_TAGPATH = f"{COMMUNITY_RATING_TAG}.{RATING_COUNT_TAG}"

METRON_COMMUNITY_RATING_TRANSFORM_TO_CB = MetaSpec(
    key_map={
        COMMUNITY_RATING_AVERAGE_KEYPATH: AVERAGE_RATING_TAGPATH,
        COMMUNITY_RATING_COUNT_KEYPATH: RATING_COUNT_TAGPATH,
    }
)


def _community_rating_from_cb(community_rating: dict[str, Any]) -> dict | None:
    # The XSD requires AverageRating inside CommunityRating.
    average_rating = community_rating.get(AVERAGE_RATING_KEY)
    if is_empty(average_rating):
        return None
    metron_community_rating = {AVERAGE_RATING_TAG: average_rating}
    rating_count = community_rating.get(RATING_COUNT_KEY)
    if not is_empty(rating_count):
        metron_community_rating[RATING_COUNT_TAG] = rating_count
    return metron_community_rating


METRON_COMMUNITY_RATING_TRANSFORM_FROM_CB = MetaSpec(
    key_map={COMMUNITY_RATING_TAG: COMMUNITY_RATING_KEY},
    spec=_community_rating_from_cb,
)
