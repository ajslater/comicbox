"""Comic Book Info transform to and from Comicbox format."""

from decimal import Decimal
from math import ceil, floor
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    ComicBookInfoSchema,
)
from comicbox.schemas.comicbox_mixin import (
    GENRES_KEY,
    ISSUE_KEY,
    ISSUE_NUMBER_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
)
from comicbox.transforms.comicbookinfo_credits import ComicBookInfoCreditsTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin


class ComicBookInfoTransform(
    ComicBookInfoCreditsTransformMixin,
    JsonTransform,
    NestedPublishingTagsMixin,
    TitleStoriesMixin,
):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    TRANSFORM_MAP = frozenbidict(
        {
            "comments": SUMMARY_KEY,
            # "country": COUNTRY_KEY, same
            # "credits": "credits_list", coded
            # "issue": ISSUE_KEY, coded
            # "language": LANGUAGE_KEY, coded
            # "numberOfVolumes": "volume_count", coded
            # "numberOfIssues": ISSUE_COUNT_KEY, coded
            "pages": PAGE_COUNT_KEY,
            "publicationDay": "day",
            "publicationMonth": "month",
            "publicationYear": "year",
            # "publisher": "publisher", coded
            "rating": "critical_rating",
            # "series": SERIES_KEY, coded
            # TAGS_KEY: TAGS_KEY, coded
            # "title": "title", coded
            # "volume": VOLUME_KEY, coded
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            "genre": GENRES_KEY,
            "tags": TAGS_KEY,
        }
    )
    CREDITS_TAG = CREDITS_TAG
    PUBLISHER_TAG = "publisher"
    SERIES_TAG = "series"
    VOLUME_COUNT_TAG = "numberOfVolumes"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = "numberOfIssues"
    TITLE_TAG = "title"
    ISSUE_TAG = "issue"
    TAGGER_TAG = "appID"
    UPDATED_AT_TAG = "lastModified"
    TOP_TAG_MAP = MappingProxyType(
        {TAGGER_KEY: TAGGER_TAG, UPDATED_AT_KEY: UPDATED_AT_TAG}
    )

    def parse_issue(self, data) -> dict:
        """Parse Issue integer."""
        issue_number = data.get(self.ISSUE_TAG)
        if issue_number is None:
            return data
        data[ISSUE_KEY] = str(issue_number)
        data[ISSUE_NUMBER_KEY] = Decimal(issue_number)
        return data

    def unparse_issue(self, data: dict) -> dict:
        """Parse Issue into an integer."""
        issue_number = data.get(ISSUE_NUMBER_KEY)
        if issue_number is None:
            return data
        # Discard decimal places
        issue_number = floor(issue_number) if issue_number >= 0 else ceil(issue_number)
        data[self.ISSUE_TAG] = issue_number
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.parse_credits,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
        parse_issue,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.unparse_credits,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        unparse_issue,
    )
