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
    NAME_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_INDEX_KEY,
    REPRINTS_KEY,
    SERIES_GROUPS_KEY,
    SERIES_KEY,
    STORIES_KEY,
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
    SERIES_ALIASES_TAG,
    SERIES_ID_KEY,
    STORY_ARC_TAG,
    TAG_ORIGIN_KEY,
    TITLE_ALIASES_TAG,
    ComictaggerSchema,
)
from comicbox.schemas.identifier import NSS_KEY
from comicbox.transforms.base import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.comicbookinfo_credits import ComicBookInfoCreditsTransformMixin
from comicbox.transforms.comicinfo_pages import comicinfo_pages_transform
from comicbox.transforms.comicinfo_storyarcs import ComicInfoStoryArcsTransformMixin
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
    ComicBookInfoCreditsTransformMixin,
    CoMetReprintsTransformMixin,
    ComicInfoStoryArcsTransformMixin,
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
                        "arcs",
                        "credits",
                        "country",
                        "day",
                        "identifiers",
                        "issue",
                        "issue_number",
                        "identifier_primary_source",
                        "language",
                        "reprints",
                        "month",
                        "notes",
                        "page_count",
                        "tagger",
                        "updated_at",
                        "year",
                    }
                    | {
                        "identifier",
                        "is_version_of",
                        "issue_id",
                        "seriesId",
                        "web_link",
                        "story_arcs",
                        "tag_origin",
                    }
                },
            }
        ),
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
        price_key_transform("price"),
        stories_key_transform("title"),
        comicinfo_pages_transform(_PAGE_TRANSFORM_MAP),
    )
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    PAGES_TAG = PAGES_TAG
    PAGES_SUB_TAG = ""
    INDEX_TAG = INDEX_TAG
    STORY_ARC_TAG = STORY_ARC_TAG
    STORY_ARC_NUMBER_TAG = ""
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

    def parse_reprints(self, data: dict) -> dict:
        """Parse series aliases and title aliases into reprints."""
        data = super().parse_reprints(data)
        reprints = []
        if series_aliases := data.get(SERIES_ALIASES_TAG):
            for series_alias in series_aliases:
                reprint = {SERIES_KEY: series_alias}
                reprints.append(reprint)

        if title_aliases := data.get(TITLE_ALIASES_TAG):
            for title_alias in title_aliases:
                stories = title_alias.split(";")
                reprint = {STORIES_KEY: stories}
                reprints.append(reprint)

        if reprints:
            reprints = data.get(REPRINTS_KEY, []) + reprints
            data[REPRINTS_KEY] = reprints
        return data

    def unparse_reprints(self, data: dict) -> dict:
        """Unparse reprints into series aliases and title aliases."""
        data = super().unparse_reprints(data)
        reprints = data.get(REPRINTS_KEY, [])
        series_aliases = set()
        title_aliases = set()
        for reprint in reprints:
            if series_name := reprint.get(SERIES_KEY, {}).get(NAME_KEY):
                series_aliases.add(series_name)
            if story_names := reprint.get(STORIES_KEY, {}).keys():
                title = ";".join(story_names)
                title_aliases.add(title)
        if series_aliases:
            series_aliases = data.get(SERIES_ALIASES_TAG, set()) | series_aliases
            data[SERIES_ALIASES_TAG] = series_aliases
        if title_aliases:
            title_aliases = data.get(TITLE_ALIASES_TAG, set()) | title_aliases
            data[TITLE_ALIASES_TAG] = title_aliases
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.parse_credits,
        parse_reprints,
        ComicInfoStoryArcsTransformMixin.parse_arcs,
        parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.unparse_credits,
        CoMetReprintsTransformMixin.unparse_reprints,
        unparse_reprints,
        ComicInfoStoryArcsTransformMixin.unparse_arcs,
        unparse_identifiers,
    )
