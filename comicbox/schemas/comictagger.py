"""Export comicbox.schemas to comicapi metadata."""
from copy import deepcopy
from types import MappingProxyType

from marshmallow import pre_dump
from marshmallow.fields import Nested

from comicbox.fields.fields import StringField
from comicbox.identifiers import IDENTIFIER_URN_NIDS, SERIES_SUFFIX
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    IDENTIFIERS_KEY,
    PAGE_COUNT_KEY,
    PAGES_KEY,
    TAGS_KEY,
)
from comicbox.schemas.comicinfo_storyarcs import (
    STORY_ARC_KEY,
    ComicInfoStoryArcsSchemaMixin,
)

TAG_ORIGIN_KEY = "tag_origin"
ISSUE_ID_KEY = "issue_id"
SERIES_ID_KEY = "series_id"


CT_DATA_KEY_MAP = MappingProxyType(
    # https://github.com/comictagger/comictagger/blob/develop/comicapi/genericmetadata.py
    {
        TAG_ORIGIN_KEY: TAG_ORIGIN_KEY,
        ISSUE_ID_KEY: ISSUE_ID_KEY,
        SERIES_ID_KEY: SERIES_ID_KEY,
        ###
        "series": "series",
        "seriesAliases": "series_aliases",
        "issue": "issue",
        "title": "title",
        "titleAliases": "title_aliases",
        "publisher": "publisher",
        "month": "month",
        "year": "year",
        "day": "day",
        "issueCount": "issue_count",
        "volume": "volume",
        "genres": "genres",
        "language": "language",
        "description": "summary",
        ###
        "volumeCount": "volume_count",
        "criticalRating": "critical_rating",
        "country": "country",
        ###
        "alternateSeries": "alternate_series",
        "alternateNumber": "alternate_issue",
        "alternateCount": "alternate_issue_count",
        "imprint": "imprint",
        "notes": "notes",
        "webLink": "web",
        "format": "original_format",
        "manga": "manga",
        "blackAndWhite": "monochrome",
        "pageCount": PAGE_COUNT_KEY,
        "maturityRating": "age_rating",
        ###
        "storyArcs": STORY_ARC_KEY,
        "seriesGroups": "series_group",
        "scanInfo": "scan_info",
        ###
        "characters": "characters",
        "teams": "teams",
        "locations": "locations",
        ###
        "alternateImages": "alternate_images",
        "credits": "credits_list",
        "tags": TAGS_KEY,
        "pages": PAGES_KEY,
        ###
        "price": "price",
        "isVersionOf": "alternate_series",
        "rights": "rights",
        "lastMark": "last_mark",
        "coverImage": "cover_image",
    }
)

CT_EXTRA_KEYS = (CONTRIBUTORS_KEY,)


class TagOriginSchema(BaseSchema):
    """Comictagger Tag Origin."""

    id = StringField()  # noqa A003
    name = StringField()


class ComictaggerSchema(ComicBookInfoSchema, ComicInfoStoryArcsSchemaMixin):
    """Comictagger schema."""

    DATA_KEY_MAP = CT_DATA_KEY_MAP
    ROOT_TAG = "comictagger"
    ROOT_TAGS = MappingProxyType({ROOT_TAG: {}})
    CONFIG_KEYS = frozenset({"comictagger", "ct"})
    FILENAME = "comictagger.json"

    tag_origin = Nested(TagOriginSchema())
    issue_id = StringField()
    series_id = StringField()

    class Meta(ComicBookInfoSchema.Meta):
        """Schema options."""

        fields = ComicBookInfoSchema.Meta.create_fields(CT_DATA_KEY_MAP, CT_EXTRA_KEYS)

    @pre_dump
    def dump_comictag_identifiers(self, data, **_kwargs):
        """Translate identifiers dict to comictagger tag_origin and ids."""
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return data
        for identifier_type in IDENTIFIER_URN_NIDS:
            issue_id = data.get(identifier_type)
            series_type = identifier_type + SERIES_SUFFIX
            series_id = data.get(series_type)
            if issue_id or series_id:
                break
        else:
            return data

        data = data(deepcopy(dict(data)))
        tag_origin = {"id": "", "name": identifier_type}
        data[TAG_ORIGIN_KEY] = tag_origin
        if issue_id:
            data[ISSUE_ID_KEY] = issue_id
        if series_id:
            data[SERIES_ID_KEY] = series_id
        return data
