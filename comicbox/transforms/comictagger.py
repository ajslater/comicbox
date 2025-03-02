"""Comictagger transform to and from Comicbox format."""

from types import MappingProxyType

from bidict import frozenbidict

from comicbox.identifiers import (
    COMICVINE_NID,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    GENRES_KEY,
    IDENTIFIERS_KEY,
    LOCATIONS_KEY,
    MONOCHROME_KEY,
    ORIGINAL_FORMAT_KEY,
    SERIES_GROUPS_KEY,
    SERIES_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
)
from comicbox.schemas.comictagger import (
    IDENTIFIER_TAG,
    INDEX_TAG,
    IS_VERSION_OF_TAG,
    ISSUE_ID_KEY,
    PAGES_TAG,
    SERIES_ID_KEY,
    STORY_ARC_TAG,
    TAG_ORIGIN_KEY,
    ComictaggerSchema,
)
from comicbox.schemas.identifier import NSS_KEY
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.comicbookinfo_credits import ComicBookInfoCreditsTransformMixin
from comicbox.transforms.comicinfo_age_rating import ComicInfoAgeRatingTransform
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.comicinfo_storyarcs import ComicInfoStoryArcsTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.price_mixin import PriceTransformMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.urns import (
    IDENTIFIER_URN_NIDS,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
)


class ComictaggerTransform(
    ComicBookInfoCreditsTransformMixin,
    ComicInfoPagesTransformMixin,
    CoMetReprintsTransformMixin,
    ComicInfoStoryArcsTransformMixin,
    IdentifiersTransformMixin,
    JsonTransform,
    NestedPublishingTagsMixin,
    TitleStoriesMixin,
    PriceTransformMixin,
    ComicInfoAgeRatingTransform,
):
    """Comictagger transform."""

    SCHEMA_CLASS = ComictaggerSchema

    TRANSFORM_MAP = frozenbidict(
        {
            # "tagOrigin": TAG_ORIGIN_KEY, code
            # "issueId": ISSUE_ID_KEY, code
            # "seriesId": SERIES_ID_KEY, code
            "description": SUMMARY_KEY,
            # "web_link": WEB_KEY, code
            "format": ORIGINAL_FORMAT_KEY,
            "black_and_white": MONOCHROME_KEY,
            "maturity_rating": AGE_RATING_KEY,
            # "story_arcs": STORY_ARC_KEY,  (copy from comicinfo)
            # "credits": "credits_list", (copy from cbi, with different tags)
            # "pages": PAGES_KEY, (copy from comicinfo)
            # "is_version_of": (copy from comet with different tags)
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            "characters": CHARACTERS_KEY,
            "genres": GENRES_KEY,
            "locations": LOCATIONS_KEY,
            "series_group": SERIES_GROUPS_KEY,
            "tags": TAGS_KEY,
            "teams": TEAMS_KEY,
        }
    )
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    PAGES_TAG = PAGES_TAG
    PAGES_SUB_TAG = ""
    INDEX_TAG = INDEX_TAG
    PAGE_TRANSFORM = frozenbidict(
        {
            "Image": "index",
            "Type": "page_type",
            "DoublePage": "double_page",
            "ImageSize": "size",
            "Key": "key",
            "Bookmark": "bookmark",
            "ImageWidth": "width",
            "ImageHeight": "height",
        }
    )
    STORY_ARC_TAG = STORY_ARC_TAG
    STORY_ARC_NUMBER_TAG = ""
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None
    PUBLISHER_TAG = "publisher"
    IMPRINT_TAG = "imprint"
    SERIES_TAG = "series"
    VOLUME_COUNT_TAG = "volume_count"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = "issue_count"
    URLS_TAG = "web_link"
    TITLE_TAG = "title"
    AGE_RATING_TAG = "maturity_rating"

    def parse_identifiers(self, data):
        """Parse comictagger tag_origin and ids to identifiers."""
        # NID
        tag_origin = data.pop(TAG_ORIGIN_KEY, None)
        tag_origin_name = tag_origin.get("name") if tag_origin else ""
        nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(
            tag_origin_name.lower(), COMICVINE_NID
        )
        self.assign_identifier_primary_source(data, nid)

        # ISSUE IDENTIFIER
        if issue_id := data.pop(ISSUE_ID_KEY, None):
            identifier = create_identifier(nid, issue_id)
            if IDENTIFIERS_KEY not in data:
                data[IDENTIFIERS_KEY] = {}
            data[IDENTIFIERS_KEY][nid] = identifier

        # SERIES_IDENTIFIER
        if series_id := data.pop(SERIES_ID_KEY, None):
            if SERIES_KEY not in data:
                data[SERIES_KEY] = {}
            if IDENTIFIERS_KEY not in data[SERIES_KEY]:
                data[:SERIES_KEY][IDENTIFIERS_KEY] = {}
            identifier = create_identifier(nid, series_id)
            data[SERIES_KEY][IDENTIFIERS_KEY][nid] = identifier

        return super().parse_identifiers(data)

    def unparse_identifiers(self, data):
        """Translate identifiers dict to comictagger tag_origin and ids."""
        issue_id = None
        series_id = None
        selected_nid = None
        identifiers = data.get(IDENTIFIERS_KEY, {})
        series_identifiers = data.get(SERIES_KEY, {}).get(IDENTIFIERS_KEY, {})
        if primary_nid := self.get_primary_source_nid(data):
            tag_origin = {"id": "", "name": primary_nid}
            data[TAG_ORIGIN_KEY] = tag_origin

        if identifiers or series_identifiers:
            for nid in (primary_nid, *IDENTIFIER_URN_NIDS):
                if not issue_id and (nss := identifiers.get(nid, {}).get(NSS_KEY)):
                    issue_id = nss
                    selected_nid = nid
                if not series_id and (
                    series_nss := series_identifiers.get(nid, {}).get(NSS_KEY)
                ):
                    series_id = series_nss
                    if not selected_nid:
                        selected_nid = nid
                if issue_id and series_id:
                    break

        if issue_id:
            data[ISSUE_ID_KEY] = issue_id
        if series_id:
            data[SERIES_ID_KEY] = series_id

        return super().unparse_identifiers(data)

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.parse_credits,
        CoMetReprintsTransformMixin.parse_reprints,
        ComicInfoPagesTransformMixin.parse_pages,
        ComicInfoStoryArcsTransformMixin.aggregate_story_arcs,
        parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_imprint,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
        PriceTransformMixin.parse_price,
        ComicInfoAgeRatingTransform.parse_age_rating,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.unparse_credits,
        CoMetReprintsTransformMixin.unparse_reprints,
        ComicInfoPagesTransformMixin.unparse_pages,
        ComicInfoStoryArcsTransformMixin.disaggregate_story_arcs,
        unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_imprint,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        PriceTransformMixin.unparse_price,
        ComicInfoAgeRatingTransform.unparse_age_rating,
    )
