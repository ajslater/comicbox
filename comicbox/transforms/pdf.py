"""Mimic comicbox.Comicbox functions for PDFs."""

from collections.abc import Mapping, Sequence
from logging import getLogger
from types import MappingProxyType
from xml.sax.saxutils import unescape

from bidict import frozenbidict

from comicbox.dict_funcs import deep_update
from comicbox.fields.collection_fields import StringSetField
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
    VOLUME_KEY,
    ComicboxSchemaMixin,
)
from comicbox.schemas.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo import MetronRoleEnum
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.credit_role_tag import GenericRoleAliases
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.xml_transforms import XmlTransform

_KEYWORDS_TRANSFORM_CLASSES = (
    # Different order than all sources
    # Doesn't include PDF.
    ComicInfoTransform,
    MetronInfoTransform,
    ComicboxJsonTransform,
    ComicboxYamlTransform,
    ComicBookInfoTransform,
    CoMetTransform,
    ComictaggerTransform,
    FilenameTransform,
)
LOG = getLogger(__name__)


class PDFXmlTransform(XmlTransform, TitleStoriesMixin):
    """PDF Schema."""

    SCHEMA_CLASS = PDFXmlSchema
    AUTHOR_TAG = "pdf:Author"
    TRANSFORM_MAP = frozenbidict(
        {
            # "pdf:Author": coded
            "pdf:Creator": SCAN_INFO_KEY,  # original document creator
            "pdf:Producer": TAGGER_KEY,
            # "pdf:Title": coded
        }
    )
    TAGS_TAG = "pdf:Keywords"
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            # TAGS_TAG: TAGS_KEY, specal code below
            "pdf:Subject": GENRES_KEY,
        }
    )
    GROUP_KEYS = frozenset(
        {PUBLISHER_KEY, IMPRINT_KEY, SERIES_KEY, VOLUME_KEY, ISSUE_KEY}
    )
    GROUP_TAG_DELIMETER = ":"
    TITLE_TAG = "pdf:Title"
    TITLE_STORIES_DELIMITER = ";"
    LIST_KEYS = frozenset({TAGS_KEY})
    AUTHOR_VALUES = frozenset(
        {
            enum.value
            for enum in (
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

    def _parse_metadata_from_tags(self, data, transform_class):
        """Parse comicinfo from keywords."""
        tags = data.get(self.TAGS_TAG)
        transform = transform_class(self._path)
        schema_cls = transform.SCHEMA_CLASS
        try:
            if issubclass(transform_class, XmlTransform):
                tags = unescape(tags)
            if (
                (cix_md := schema_cls().loads(tags))
                and (md := transform.to_comicbox(cix_md))
                and (sub_md := md.get(ComicboxSchemaMixin.ROOT_TAG))
            ):
                data.pop(TAGS_KEY, None)
                deep_update(data, sub_md)
                return True
        except Exception as exc:
            LOG.debug(
                f"Failed to parse {schema_cls.__name__} from keywords in {self._path}: {exc}"
            )
        return False

    def _parse_comma_delimited_tags(self, data):
        if tags := data.get(self.TAGS_TAG):
            tags = StringSetField()._deserialize(tags, self.TAGS_TAG, data)  # noqa: SLF001
            data[self.TAGS_TAG] = tags

    def parse_tags(self, data):
        """Parse different possible keyword schemas."""
        for transform_class in _KEYWORDS_TRANSFORM_CLASSES:
            if self._parse_metadata_from_tags(data, transform_class):
                return data
        # Comma delimited string
        self._parse_comma_delimited_tags(data)
        self.string_list_to_dicts_one(data, self.TAGS_TAG, TAGS_KEY)
        return data

    def unparse_tags(self, data):
        """Stuff comicinfo into keywords."""
        transform = self._transform_class(self._path)
        schema = transform.SCHEMA_CLASS()
        if (md := transform.from_comicbox(data)) and (tags := schema.dumps(md)):
            data[self.TAGS_TAG] = tags
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_tags,
        parse_credits,
        TitleStoriesMixin.parse_stories,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        unparse_tags,
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        unparse_credits,
        TitleStoriesMixin.unparse_stories,
    )

    def from_comicbox(
        self, data: Mapping, write_transforms: Sequence[BaseTransform] = (), **kwargs
    ) -> MappingProxyType:
        """Override for specifying transform class."""
        if (
            ComicboxJsonTransform in write_transforms
            and ComicInfoTransform not in write_transforms
        ):
            self._transform_class = ComicboxJsonTransform
        else:
            self._transform_class = ComicInfoTransform
        return super().from_comicbox(data, **kwargs)


class MuPDFTransform(PDFXmlTransform):
    """MuPDF Transformer."""

    SCHEMA_CLASS = MuPDFSchema
    AUTHOR_TAG = "author"
    TITLE_TAG = "title"
    TAGS_TAG = "keywords"
    TRANSFORM_MAP = frozenbidict(
        {
            # AUTHOR_TAG: CONTRIBUTORS_KEY,
            "creator": SCAN_INFO_KEY,  # original document creator
            "producer": TAGGER_KEY,
            # "title": "title", coded
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            # "keywords": TAGS_KEY, code
            "subject": GENRES_KEY,
        }
    )
    LIST_KEYS = frozenset({TAGS_KEY})
