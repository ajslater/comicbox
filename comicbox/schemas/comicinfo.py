"""A class to encapsulate ComicRack's ComicInfo.xml data."""
from logging import getLogger
from types import MappingProxyType

from stringcase import pascalcase

from comicbox.fields.collections import (
    IdentifiersField,
    StringSetField,
)
from comicbox.fields.enum import YesNoField
from comicbox.identifiers import GTIN_NID, GTIN_NID_ORDER
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    IDENTIFIERS_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    PAGES_KEY,
    STORY_ARCS_KEY,
    TAGS_KEY,
)
from comicbox.schemas.comicinfo_storyarcs import (
    STORY_ARC_KEY,
    STORY_ARC_NUMBER_KEY,
    ComicInfoStoryArcsSchemaMixin,
)
from comicbox.schemas.contributors import get_case_credit_map
from comicbox.schemas.xml_credits import ComicXmlCreditsSchema

LOG = getLogger(__name__)

_CIX_CREDIT_KEY_MAP = get_case_credit_map(pascalcase)
_CIX_DATA_KEY_MAP = MappingProxyType(
    {
        "AgeRating": "age_rating",
        "AlternateCount": "alternate_issue_count",
        "AlternateNumber": "alternate_issue",
        "AlternateSeries": "alternate_series",
        "BlackAndWhite": "monochrome",
        "Characters": "characters",
        "CommunityRating": "community_rating",
        "Country": "country",
        "Count": "issue_count",
        "Day": "day",
        "Genre": "genres",
        "GTIN": IDENTIFIERS_KEY,
        "Format": "original_format",
        "Imprint": "imprint",
        "LanguageISO": "language",
        "Locations": "locations",
        "MainCharacterOrTeam": "protagonist",
        "Manga": "manga",
        "Month": "month",
        "Notes": NOTES_KEY,
        "Number": "issue",
        "PageCount": PAGE_COUNT_KEY,  # recaluculated by comicbox
        "Pages": PAGES_KEY,
        "Publisher": "publisher",
        "Review": "review",
        "ScanInformation": "scan_info",
        "Series": "series",
        "SeriesGroup": "series_groups",
        "StoryArc": STORY_ARC_KEY,
        "StoryArcNumber": STORY_ARC_NUMBER_KEY,
        "Tags": TAGS_KEY,
        "Teams": "teams",
        "Title": "title",
        "Summary": "summary",
        "Volume": "volume",
        "Web": "web",
        "Year": "year",
        **_CIX_CREDIT_KEY_MAP,
    }
)
_CIX_EXTRA_KEYS = (CONTRIBUTORS_KEY, STORY_ARCS_KEY)


class ComicInfoSchema(ComicXmlCreditsSchema, ComicInfoStoryArcsSchemaMixin):
    """ComicInfo.xml Schema."""

    DATA_KEY_MAP = _CIX_DATA_KEY_MAP
    CREDIT_KEY_MAP = _CIX_CREDIT_KEY_MAP
    ROOT_TAG = "ComicInfo"
    ROOT_TAGS = MappingProxyType(
        {
            ROOT_TAG: {
                "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
                "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "@xsi:schemaLocation": "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1",
            }
        }
    )
    CONFIG_KEYS = frozenset(
        {"cr", "ci", "cix", "comicinfo", "comicinfoxml", "comicrack"}
    )
    FILENAME = "comicinfo.xml"
    PAGE_INFO_KEY_MAP = MappingProxyType(
        {
            "@Image": "index",
            "@Type": "page_type",
            "@DoublePage": "double_page",
            "@ImageSize": "size",
            "@Key": "key",
            "@Bookmark": "bookmark",
            "@ImageWidth": "width",
            "@ImageHeight": "height",
        }
    )

    monochrome = YesNoField()

    colorist = StringSetField(as_string=True)
    cover = StringSetField(as_string=True)
    editor = StringSetField(as_string=True)
    inker = StringSetField(as_string=True)
    letterer = StringSetField(as_string=True)
    penciller = StringSetField(as_string=True)
    writer = StringSetField(as_string=True)

    characters = StringSetField(as_string=True)
    genres = StringSetField(as_string=True)
    locations = StringSetField(as_string=True)
    series_groups = StringSetField(as_string=True)
    tags = StringSetField(as_string=True)
    teams = StringSetField(as_string=True)

    identifiers = IdentifiersField(
        as_string_order=GTIN_NID_ORDER,
        naked_identifier_type=GTIN_NID,
    )

    class Meta(ComicXmlCreditsSchema.Meta):
        """Schema options."""

        fields = ComicXmlCreditsSchema.Meta.create_fields(
            _CIX_DATA_KEY_MAP, _CIX_EXTRA_KEYS
        )
