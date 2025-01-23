"""Comictagger transform to and from Comicbox format."""

from bidict import bidict

from comicbox.identifiers import (
    COMICVINE_NID,
    IDENTIFIER_URN_NIDS,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    IDENTIFIERS_KEY,
    ORIGINAL_FORMAT_KEY,
    SERIES_KEY,
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
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.comicinfo_storyarcs import ComicInfoStoryArcsTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin


class ComictaggerTransform(
    ComicBookInfoCreditsTransformMixin,
    ComicInfoPagesTransformMixin,
    CoMetReprintsTransformMixin,
    ComicInfoStoryArcsTransformMixin,
    IdentifiersTransformMixin,
    JsonTransform,
    NestedPublishingTagsMixin,
):
    """Comictagger transform."""

    SCHEMA_CLASS = ComictaggerSchema

    TRANSFORM_MAP = bidict(
        {
            # "tagOrigin": TAG_ORIGIN_KEY, code
            # "issueId": ISSUE_ID_KEY, code
            # "seriesId": SERIES_ID_KEY, code
            "description": "summary",
            # "web_link": WEB_KEY, code
            "format": ORIGINAL_FORMAT_KEY,
            "black_and_white": "monochrome",
            "maturity_rating": "age_rating",
            # "story_arcs": STORY_ARC_KEY,  (copy from comicinfo)
            # "credits": "credits_list", (copy from cbi, with different tags)
            # "pages": PAGES_KEY, (copy from comicinfo)
            # "is_version_of": (copy from comet with different tags)
        }
    )
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    PAGES_TAG = PAGES_TAG
    PAGES_SUB_TAG = ""
    INDEX_TAG = INDEX_TAG
    PAGE_TRANSFORM = bidict(
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
    SERIES_TAG = "series"
    VOLUME_COUNT_TAG = "volume_count"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = "issue_count"
    URL_TAG = "web_link"

    def parse_comictagger_identifiers(self, data):
        """Parse comictagger tag_origin and ids to identifiers."""
        tag_origin = data.pop(TAG_ORIGIN_KEY, None)
        issue_id = data.pop(ISSUE_ID_KEY, None)
        series_id = data.pop(SERIES_ID_KEY, None)
        if not issue_id and not series_id:
            return data

        tag_origin_name = tag_origin.get("name") if tag_origin else ""
        nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(
            tag_origin_name.lower(), COMICVINE_NID
        )
        if IDENTIFIERS_KEY not in data:
            data[IDENTIFIERS_KEY] = {}

        if issue_id:
            identifier = create_identifier(nid, issue_id)
            data[IDENTIFIERS_KEY][nid] = identifier
        if series_id:
            if SERIES_KEY not in data:
                data[SERIES_KEY] = {}
            if IDENTIFIERS_KEY not in data[SERIES_KEY]:
                data[:SERIES_KEY][IDENTIFIERS_KEY] = {}
            identifier = create_identifier(nid, series_id)
            data[SERIES_KEY][IDENTIFIERS_KEY][nid] = identifier
        return data

    def _unparse_comictagger_identifier_components(
        self, identifiers, series_identifiers
    ):
        issue_id = None
        series_id = None
        selected_nid = None
        for nid in IDENTIFIER_URN_NIDS:
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
        return issue_id, series_id, selected_nid

    def unparse_comictagger_identifiers(self, data):
        """Translate identifiers dict to comictagger tag_origin and ids."""
        identifiers = data.get(IDENTIFIERS_KEY, {})
        series_identifiers = data.get(SERIES_KEY, {}).get(IDENTIFIERS_KEY, {})
        if not identifiers and not series_identifiers:
            return data

        (
            issue_id,
            series_id,
            selected_nid,
        ) = self._unparse_comictagger_identifier_components(
            identifiers, series_identifiers
        )

        if selected_nid:
            tag_origin = {"id": "", "name": selected_nid}
            data[TAG_ORIGIN_KEY] = tag_origin
        if issue_id:
            data[ISSUE_ID_KEY] = issue_id
        if series_id:
            data[SERIES_ID_KEY] = series_id
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_comictagger_identifiers,
        ComicBookInfoCreditsTransformMixin.aggregate_contributors,
        CoMetReprintsTransformMixin.parse_reprints,
        ComicInfoPagesTransformMixin.parse_pages,
        ComicInfoStoryArcsTransformMixin.aggregate_story_arcs,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_url_tag,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        unparse_comictagger_identifiers,
        ComicBookInfoCreditsTransformMixin.disaggregate_contributors,
        CoMetReprintsTransformMixin.unparse_reprints,
        ComicInfoPagesTransformMixin.unparse_pages,
        ComicInfoStoryArcsTransformMixin.disaggregate_story_arcs,
        IdentifiersTransformMixin.unparse_url_tag,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
    )
