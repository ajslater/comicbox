"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from comicbox.schemas.comicbox_mixin import (
    EXT_KEY,
    ISSUE_KEY,
    ORIGINAL_FORMAT_KEY,
    REMAINDERS_KEY,
    SCAN_INFO_KEY,
    YEAR_KEY,
)
from comicbox.schemas.filename import FilenameSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.publishing_tags import (
    ISSUE_COUNT_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map


class FilenameTransform(BaseTransform):
    """File name schema."""

    SCHEMA_CLASS = FilenameSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "ext": EXT_KEY,
                "issue": ISSUE_KEY,
                "issue_count": ISSUE_COUNT_KEY_PATH,
                "original_format": ORIGINAL_FORMAT_KEY,
                "remainders": REMAINDERS_KEY,
                "series": SERIES_NAME_KEY_PATH,
                "scan_info": SCAN_INFO_KEY,
                "volume": VOLUME_NUMBER_KEY_PATH,
                "year": YEAR_KEY,
            }
        ),
        stories_key_transform("title"),
        format_root_key=FilenameSchema.ROOT_TAG,
    )
