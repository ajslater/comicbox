"""A class to encapsulate CoMet data."""
from types import MappingProxyType

from stringcase import camelcase

from comicbox.fields.collections import IdentifiersField, StringSetField
from comicbox.identifiers import IDENTIFIER_URN_NIDS
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    IDENTIFIERS_KEY,
    PAGE_COUNT_KEY,
)
from comicbox.schemas.contributors import (
    get_case_contributor_map,
    get_case_credit_map,
)
from comicbox.schemas.xml_credits import ComicXmlCreditsSchema


def _fix_comet_contributor_map(contributor_map):
    """Fix comet contribtuor or credit map."""
    contributor_map = dict(contributor_map)
    contributor_map["coverDesigner"] = contributor_map.pop("coverArtist")
    return MappingProxyType(contributor_map)


def get_comet_credit_map():
    """BUild a comet credit map."""
    credit_map = get_case_credit_map(camelcase)
    return _fix_comet_contributor_map(credit_map)


_COMET_CREDIT_KEY_MAP = get_comet_credit_map()
_COMET_DATA_KEY_MAP = MappingProxyType(
    {
        # http://www.denvog.com/comet/comet-specification/
        "character": "characters",
        "coverImage": "cover_image",
        "date": "date",
        "description": "summary",
        "format": "original_format",
        "genre": "genres",
        "identifier": IDENTIFIERS_KEY,
        "issue": "issue",
        "isVersionOf": "alternate_issue",
        "language": "language",
        "lastMark": "last_mark",
        "pages": PAGE_COUNT_KEY,
        "publisher": "publisher",
        "price": "price",
        "rating": "age_rating",
        "readingDirection": "reading_direction",
        "rights": "rights",
        "series": "series",
        "title": "title",
        "volume": "volume",
        **_COMET_CREDIT_KEY_MAP,
    }
)
_COMET_EXTRA_KEYS = (CONTRIBUTORS_KEY,)


def get_comet_contributor_map():
    """Build comet contributor map."""
    contributor_map = get_case_contributor_map(
        ComicXmlCreditsSchema.CONTRIBUTOR_TAGS, camelcase
    )
    return _fix_comet_contributor_map(contributor_map)


class CoMetSchema(ComicXmlCreditsSchema):
    """CoMet Schema."""

    DATA_KEY_MAP = _COMET_DATA_KEY_MAP
    CREDIT_KEY_MAP = _COMET_CREDIT_KEY_MAP
    ROOT_TAG = "comet"
    ROOT_TAGS = MappingProxyType(
        {
            ROOT_TAG: {
                "@xmlns:comet": "http://www.denvog.com/comet/",
                "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "@xsi:schemaLocation": "http://www.denvog.com/comet/comet.xsd",
            }
        }
    )
    FILENAME = "comet.xml"
    CONFIG_KEYS = frozenset({"comet"})
    CONTRIBUTOR_TAGS = get_comet_contributor_map()

    colorist = StringSetField()
    cover = StringSetField()
    creator = StringSetField()
    editor = StringSetField()
    inker = StringSetField()
    letterer = StringSetField()
    penciller = StringSetField()
    writer = StringSetField()

    identifiers = IdentifiersField(as_string_order=IDENTIFIER_URN_NIDS.keys())

    class Meta(ComicXmlCreditsSchema.Meta):
        """Schema options."""

        fields = ComicXmlCreditsSchema.Meta.create_fields(
            _COMET_DATA_KEY_MAP, _COMET_EXTRA_KEYS
        )
