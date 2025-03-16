"""Mimic comicbox.Comicbox functions for PDFs."""

from logging import getLogger

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    GENRES_KEY,
    IMPRINT_KEY,
    ISSUE_KEY,
    PUBLISHER_KEY,
    ROLES_KEY,
    SCAN_INFO_KEY,
    SERIES_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
    VOLUME_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import name_obj_to_string_list, string_list_to_name_obj
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)


class PDFXmlTransform(XmlTransform, TitleStoriesMixin):
    """PDF Schema."""

    SCHEMA_CLASS = PDFXmlSchema
    AUTHOR_TAG = "pdf:Author"
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                # "pdf:Author": coded
                "pdf:Creator": SCAN_INFO_KEY,  # original document creator
                "pdf:Producer": TAGGER_KEY,
                "pdf:ModDate": UPDATED_AT_KEY,
                # "pdf:Title": coded
            }
        ),
        KeyTransforms(
            key_map={
                # TAGS_TAG: TAGS_KEY, specal code below
                "pdf:Subject": GENRES_KEY,
            },
            to_cb=string_list_to_name_obj,
            from_cb=name_obj_to_string_list,
        ),
    )
    TAGS_TAG = "pdf:Keywords"
    GROUP_KEYS = frozenset(
        {PUBLISHER_KEY, IMPRINT_KEY, SERIES_KEY, VOLUME_KEY, ISSUE_KEY}
    )
    GROUP_TAG_DELIMETER = ":"
    TITLE_TAG = "pdf:Title"
    TITLE_STORIES_DELIMITER = ";"
    AUTHOR_VALUES = frozenset(
        {
            enum.value
            for enum in (
                GenericRoleEnum.AUTHOR,
                MetronRoleEnum.WRITER,
                MetronRoleEnum.SCRIPT,
                MetronRoleEnum.STORY,
                MetronRoleEnum.PLOT,
                MetronRoleEnum.TRANSLATOR,
                CoMetRoleTagEnum.CREATOR,
                CoMetRoleTagEnum.WRITER,
                ComicInfoRoleTagEnum.WRITER,
                ComicInfoRoleTagEnum.TRANSLATOR,
            )
        }
        | {*GenericRoleAliases.WRITER.value}
    )

    def parse_credits(self, data):
        """Convert csv to writer credits."""
        authors = data.get(self.AUTHOR_TAG)
        if not authors:
            return data
        comicbox_credits = {
            author: {ROLES_KEY: {"Writer": {}}} for author in authors if author
        }
        if comicbox_credits:
            data[CREDITS_KEY] = comicbox_credits
        return data

    def unparse_credits(self, data):
        """Convert writer credits to csv."""
        comicbox_credits = data.pop(CREDITS_KEY, {})
        authors = set()
        for person_name, comicbox_credit in comicbox_credits.items():
            if not person_name:
                continue
            comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
            for role_name in comicbox_roles:
                if role_name.lower() in self.AUTHOR_VALUES:
                    authors.add(person_name)
        if authors:
            data[self.AUTHOR_TAG] = authors
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_credits,
        TitleStoriesMixin.parse_stories,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        unparse_credits,
        TitleStoriesMixin.unparse_stories,
    )


class MuPDFTransform(PDFXmlTransform):
    """MuPDF Transformer."""

    SCHEMA_CLASS = MuPDFSchema
    AUTHOR_TAG = "author"
    TITLE_TAG = "title"
    TAGS_TAG = "keywords"
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                # AUTHOR_TAG: CONTRIBUTORS_KEY,
                "creator": SCAN_INFO_KEY,  # original document creator
                "modDate": UPDATED_AT_KEY,
                "producer": TAGGER_KEY,
                # "title": "title", coded
            }
        ),
        KeyTransforms(
            key_map={
                # "keywords": TAGS_KEY, code
                "subject": GENRES_KEY,
            },
            to_cb=string_list_to_name_obj,
            from_cb=name_obj_to_string_list,
        ),
    )
    LIST_KEYS = frozenset({TAGS_KEY})
