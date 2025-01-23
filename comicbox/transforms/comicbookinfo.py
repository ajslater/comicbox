"""Comic Book Info transform to and from Comicbox format."""

from datetime import datetime

from bidict import bidict

from comicbox.fields.time_fields import DateTimeField
from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    LAST_MODIFIED_TAG,
    ComicBookInfoSchema,
)
from comicbox.schemas.comicbox_mixin import (
    GENRES_KEY,
    PAGE_COUNT_KEY,
    UPDATED_AT_KEY,
)
from comicbox.transforms.comicbookinfo_credits import ComicBookInfoCreditsTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin


class ComicBookInfoTransform(
    ComicBookInfoCreditsTransformMixin,
    JsonTransform,
    NestedPublishingTagsMixin,
):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    TRANSFORM_MAP = bidict(
        {
            "comments": "summary",
            # "country": "country", coded
            # "credits": "credits_list", coded
            "genre": GENRES_KEY,
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
    CREDITS_TAG = CREDITS_TAG
    SERIES_TAG = "series"
    VOLUME_COUNT_TAG = "numberOfVolumes"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = "numberOfIssues"

    def unwrap(self, data, root_tags=None) -> dict:
        """Retrieve the last modified timestamp."""
        last_modified = data.get(LAST_MODIFIED_TAG)
        sub_data = super().unwrap(data, root_tags=root_tags)
        if last_modified:
            sub_data[UPDATED_AT_KEY] = last_modified
        return sub_data

    def wrap(self, sub_data, root_tags=None, stamp=False, **_kwargs):  # noqa: FBT002
        """Add the last modified timestamp."""
        updated_at = sub_data.get(UPDATED_AT_KEY) if stamp else None
        data = super().wrap(sub_data, stamp=False, root_tags=root_tags)
        if stamp:
            field = DateTimeField()
            timestamp = updated_at if updated_at is not None else datetime.utcnow()  # noqa: DTZ003
            last_modified = field._serialize(timestamp)  # noqa: SLF001
            if last_modified:
                data[LAST_MODIFIED_TAG] = last_modified
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.aggregate_contributors,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.disaggregate_contributors,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
    )
