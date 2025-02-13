"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from comicbox.schemas.filename import FilenameSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_stories_mixin import TitleStoriesMixin


class FilenameTransform(BaseTransform, NestedPublishingTagsMixin, TitleStoriesMixin):
    """File name schema."""

    SCHEMA_CLASS = FilenameSchema
    SERIES_TAG = "series"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = "issue_count"
    TITLE_TAG = "title"

    TO_COMICBOX_PRE_TRANSFORM = (
        *BaseTransform.TO_COMICBOX_PRE_TRANSFORM,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *BaseTransform.FROM_COMICBOX_PRE_TRANSFORM,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
    )
