"""Comic Book Info transform to and from Comicbox format."""

from datetime import datetime
from decimal import Decimal
from math import ceil, floor
from types import MappingProxyType

from bidict import bidict

from comicbox.fields.time_fields import DateTimeField
from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    LAST_MODIFIED_TAG,
    ComicBookInfoSchema,
)
from comicbox.schemas.comicbox_mixin import (
    GENRES_KEY,
    ISSUE_KEY,
    ISSUE_NUMBER_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
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
    TRANSFORM_MAP = bidict(
        {
            "comments": SUMMARY_KEY,
            # "country": "country", coded
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

    def unwrap(self, data, wrap_tags=None) -> dict:
        """Retrieve the last modified timestamp."""
        last_modified = data.get(LAST_MODIFIED_TAG)
        sub_data = super().unwrap(data, wrap_tags=wrap_tags)
        if last_modified:
            sub_data[UPDATED_AT_KEY] = last_modified
        return sub_data

    def wrap(self, sub_data, wrap_tags=None, stamp=False, **_kwargs):  # noqa: FBT002
        """Add the last modified timestamp."""
        updated_at = sub_data.get(UPDATED_AT_KEY) if stamp else None
        data = super().wrap(sub_data, stamp=False, wrap_tags=wrap_tags)
        if stamp:
            field = DateTimeField()
            timestamp = updated_at if updated_at is not None else datetime.utcnow()  # noqa: DTZ003
            last_modified = field._serialize(timestamp)  # noqa: SLF001
            if last_modified:
                data[LAST_MODIFIED_TAG] = last_modified
        return data

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
