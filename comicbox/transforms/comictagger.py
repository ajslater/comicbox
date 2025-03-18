"""Comictagger transform to and from Comicbox format."""

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
    PAGE_INDEX_KEY,
    SERIES_GROUPS_KEY,
    SERIES_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
)
from comicbox.schemas.comictagger import (
    IDENTIFIER_TAG,
    INDEX_TAG,
    ISSUE_ID_KEY,
    SERIES_ID_KEY,
    STORY_ARC_TAG,
    TAG_ORIGIN_KEY,
    ComictaggerSchema,
)
from comicbox.schemas.identifier import NSS_KEY
from comicbox.transforms.base import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.comet_reprints import comet_reprints_transform
from comicbox.transforms.comicbookinfo_credits import cbi_credits_transform
from comicbox.transforms.comicinfo_pages import comicinfo_pages_transform
from comicbox.transforms.comicinfo_storyarcs import story_arcs_transform
from comicbox.transforms.comictagger_reprints import (
    CT_SERIES_ALIASES_KEY_TRANSFORM,
    CT_TITLE_ALIASES_KEY_TRANSFORM,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.price import price_key_transform
from comicbox.transforms.publishing_tags import (
    IMPRINT_NAME_KEY_PATH,
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_COUNT_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.urns import (
    IDENTIFIER_URN_NIDS,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
)

_PAGE_TRANSFORM_MAP = create_transform_map(
    KeyTransforms(
        key_map={
            "Image": PAGE_INDEX_KEY,
            "Type": "page_type",
            "DoublePage": "double_page",
            "ImageSize": "size",
            "Key": "key",
            "Bookmark": "bookmark",
            "ImageWidth": "width",
            "ImageHeight": "height",
        }
    )
)


class ComictaggerTransform(
    IdentifiersTransformMixin,
    JsonTransform,
):
    """Comictagger transform."""

    SCHEMA_CLASS = ComictaggerSchema

    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "publisher": PUBLISHER_NAME_KEY_PATH,
                "imprint": IMPRINT_NAME_KEY_PATH,
                "series": SERIES_NAME_KEY_PATH,
                "volume_count": VOLUME_COUNT_KEY_PATH,
                "volume": VOLUME_NUMBER_KEY_PATH,
                "issue_count": ISSUE_COUNT_KEY_PATH,
                # "tagOrigin": CODE
                # "issueId": CODE
                # "seriesId": CODE
                "description": SUMMARY_KEY,
                # "web_link": CODE
                "format": ORIGINAL_FORMAT_KEY,
                "black_and_white": MONOCHROME_KEY,
                "maturity_rating": AGE_RATING_KEY,
                # "story_arcs": CODE
                # "credits": CODE
                # "pages": CODE
                # "is_version_of": CODE
                **{
                    key: key
                    for key in {
                        "country",
                        "day",
                        "identifiers",
                        "issue",
                        "issue_number",
                        "identifier_primary_source",
                        "language",
                        "month",
                        "notes",
                        "page_count",
                        "tagger",
                        "updated_at",
                        "year",
                    }
                    | {
                        "identifier",
                        ISSUE_ID_KEY,
                        SERIES_ID_KEY,
                        "web_link",
                        "tag_origin",
                    }
                },
            }
        ),
        cbi_credits_transform("credits"),
        name_obj_to_string_list_key_transforms(
            {
                "characters": CHARACTERS_KEY,
                "genres": GENRES_KEY,
                "locations": LOCATIONS_KEY,
                "series_group": SERIES_GROUPS_KEY,
                "tags": TAGS_KEY,
                "teams": TEAMS_KEY,
            }
        ),
        comicinfo_pages_transform("pages", _PAGE_TRANSFORM_MAP),
        price_key_transform("price"),
        comet_reprints_transform("is_version_of"),
        CT_SERIES_ALIASES_KEY_TRANSFORM,
        CT_TITLE_ALIASES_KEY_TRANSFORM,
        stories_key_transform("title"),
        story_arcs_transform(STORY_ARC_TAG, ""),
    )
    INDEX_TAG = INDEX_TAG
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None
    URLS_TAG = "web_link"

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
        parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        unparse_identifiers,
    )
