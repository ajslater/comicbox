"""Mimic comicbox.Comicbox functions for PDFs."""

from logging import getLogger

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    GENRES_KEY,
    ROLES_KEY,
    SCAN_INFO_KEY,
    TAGGER_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.base import (
    BaseTransform,
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map

LOG = getLogger(__name__)

_AUTHOR_VALUES = frozenset(
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


def _authors_to_credits(_source_data, authors):
    return {author: {ROLES_KEY: {"Writer": {}}} for author in authors if author}


def _credits_to_authors(_source_data, comicbox_credits):
    authors = set()
    for person_name, comicbox_credit in comicbox_credits.items():
        if not person_name:
            continue
        comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
        for role_name in comicbox_roles:
            if role_name.lower() in _AUTHOR_VALUES:
                authors.add(person_name)
    return authors


def authors_to_credits_transform(author_tag):
    """Create a Transform for pdf authors to comicbox credits."""
    return KeyTransforms(
        key_map={author_tag: CREDITS_KEY},
        to_cb=_authors_to_credits,
        from_cb=_credits_to_authors,
    )


class PDFXmlTransform(BaseTransform):
    """PDF Schema."""

    SCHEMA_CLASS = PDFXmlSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "pdf:Creator": SCAN_INFO_KEY,  # original document creator
                "pdf:Producer": TAGGER_KEY,
                "pdf:ModDate": UPDATED_AT_KEY,
            }
        ),
        authors_to_credits_transform("pdf:Author"),
        name_obj_to_string_list_key_transforms(
            {
                "pdf:Subject": GENRES_KEY,
            },
        ),
        stories_key_transform("pdf:Title"),
        format_root_key_path_path=PDFXmlSchema.ROOT_KEY_PATH,
    )


class MuPDFTransform(PDFXmlTransform):
    """MuPDF Transformer."""

    SCHEMA_CLASS = MuPDFSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "creator": SCAN_INFO_KEY,  # original document creator
                "modDate": UPDATED_AT_KEY,
                "producer": TAGGER_KEY,
            }
        ),
        authors_to_credits_transform("author"),
        name_obj_to_string_list_key_transforms(
            {
                "subject": GENRES_KEY,
            },
        ),
        stories_key_transform("title"),
        format_root_key_path_path=MuPDFSchema.ROOT_KEY_PATH,
    )
