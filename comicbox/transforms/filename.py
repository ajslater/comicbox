"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    EXT_KEY,
    ORIGINAL_FORMAT_KEY,
    REMAINDERS_KEY,
    SCAN_INFO_KEY,
    TITLE_KEY,
)
from comicbox.schemas.filename import FilenameSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import ISSUE_NAME_KEYPATH, YEAR_KEYPATH
from comicbox.transforms.publishing_tags import (
    ISSUE_COUNT_KEYPATH,
    SERIES_NAME_KEYPATH,
    VOLUME_NUMBER_KEYPATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

SIMPLE_KEY_MAP = frozenbidict(
    {
        "ext": EXT_KEY,
        "issue": ISSUE_NAME_KEYPATH,
        "issue_count": ISSUE_COUNT_KEYPATH,
        "original_format": ORIGINAL_FORMAT_KEY,
        "remainders": REMAINDERS_KEY,
        "series": SERIES_NAME_KEYPATH,
        "scan_info": SCAN_INFO_KEY,
        "title": TITLE_KEY,
        "volume": VOLUME_NUMBER_KEYPATH,
        "year": YEAR_KEYPATH,
    }
)


class FilenameTransform(BaseTransform):
    """File name schema."""

    SCHEMA_CLASS = FilenameSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP.inverse),
        format_root_keypath=FilenameSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        format_root_keypath=FilenameSchema.ROOT_KEYPATH,
    )
