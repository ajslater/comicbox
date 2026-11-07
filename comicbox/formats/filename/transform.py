"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from bidict import frozenbidict

from comicbox.formats.base.transforms.base import BaseTransform
from comicbox.formats.base.transforms.publishing_tags import (
    ISSUE_COUNT_KEYPATH,
    PUBLISHER_NAME_KEYPATH,
    SERIES_NAME_KEYPATH,
    VOLUME_COUNT_KEYPATH,
    VOLUME_NUMBER_KEYPATH,
)
from comicbox.formats.base.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)
from comicbox.formats.comicbox.schema import (
    EXT_KEY,
    ORIGINAL_FORMAT_KEY,
    REMAINDERS_KEY,
    SCAN_INFO_KEY,
    TITLE_KEY,
)
from comicbox.formats.comicbox.transform import (
    DAY_KEYPATH,
    ISSUE_NAME_KEYPATH,
    MONTH_KEYPATH,
    YEAR_KEYPATH,
)
from comicbox.formats.filename.schema import FilenameSchema

# The keys comicbox reads out of a filename and writes back into one.
SIMPLE_KEY_MAP = frozenbidict(
    {
        "day": DAY_KEYPATH,
        "ext": EXT_KEY,
        "issue": ISSUE_NAME_KEYPATH,
        "issue_count": ISSUE_COUNT_KEYPATH,
        "month": MONTH_KEYPATH,
        "original_format": ORIGINAL_FORMAT_KEY,
        "remainders": REMAINDERS_KEY,
        "series": SERIES_NAME_KEYPATH,
        "scan_info": SCAN_INFO_KEY,
        "title": TITLE_KEY,
        "volume": VOLUME_NUMBER_KEYPATH,
        "volume_count": VOLUME_COUNT_KEYPATH,
        "year": YEAR_KEYPATH,
    }
)
# comicfn2dict writes any publisher as "(Name)" but reads back only the ones it
# knows by name; the rest read as the title. So a publisher is read out of a
# filename and never written into one.
READ_ONLY_KEY_MAP = frozenbidict({"publisher": PUBLISHER_NAME_KEYPATH})


class FilenameTransform(BaseTransform):
    """File name schema."""

    SCHEMA_CLASS = FilenameSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map={**SIMPLE_KEY_MAP.inverse, **READ_ONLY_KEY_MAP.inverse}),
        format_root_keypath=FilenameSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        format_root_keypath=FilenameSchema.ROOT_KEYPATH,
    )
