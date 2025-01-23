"""Mimic comicbox.Comicbox functions for PDFs."""

from collections.abc import Mapping, Sequence
from logging import getLogger
from types import MappingProxyType
from xml.sax.saxutils import unescape

from bidict import bidict

from comicbox.dict_funcs import deep_update
from comicbox.fields.collection_fields import StringSetField
from comicbox.schemas.comicbox_mixin import (
    CONTRIBUTORS_KEY,
    GENRES_KEY,
    IMPRINT_KEY,
    ISSUE_KEY,
    PUBLISHER_KEY,
    ROOT_TAG,
    SCAN_INFO_KEY,
    SERIES_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    VOLUME_KEY,
    WRITER_KEY,
)
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.xml_transforms import XmlTransform

_KEYWORDS_TRANSFORM_CLASSES = (
    # Different order than all sources
    # Doesn't include PDF.
    ComicInfoTransform,
    ComicboxJsonTransform,
    ComicboxYamlTransform,
    ComicBookInfoTransform,
    MetronInfoTransform,
    CoMetTransform,
    ComictaggerTransform,
    FilenameTransform,
)
LOG = getLogger(__name__)


class PDFXmlTransform(XmlTransform):
    """PDF Schema."""

    SCHEMA_CLASS = PDFXmlSchema
    AUTHOR_TAG = "pdf:Author"
    TRANSFORM_MAP = bidict(
        {
            # AUTHOR_TAG: CONTRIBUTORS_KEY,
            "pdf:Creator": SCAN_INFO_KEY,  # original document creator
            "pdf:Keywords": TAGS_KEY,
            "pdf:Producer": TAGGER_KEY,
            "pdf:Subject": GENRES_KEY,
            "pdf:Title": "title",
        }
    )
    GROUP_KEYS = frozenset(
        {PUBLISHER_KEY, IMPRINT_KEY, SERIES_KEY, VOLUME_KEY, ISSUE_KEY}
    )
    GROUP_TAG_DELIMETER = ":"

    def aggregate_contributors(self, data):
        """Convert csv to writer credits."""
        authors = data.get(self.AUTHOR_TAG)
        if not authors:
            return data
        data[CONTRIBUTORS_KEY] = {WRITER_KEY: authors}
        return data

    def disaggregate_contributors(self, data):
        """Convert writer credits to csv."""
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        if authors := contributors.get(WRITER_KEY):
            data[self.AUTHOR_TAG] = authors
        return data

    def _parse_metadata_from_tags(self, data, transform_class):
        """Parse comicinfo from keywords."""
        tags = data.get(TAGS_KEY)
        transform = transform_class(self._path)
        schema = transform.SCHEMA_CLASS()
        try:
            if issubclass(transform_class, XmlTransform):
                tags = unescape(tags)
            if (
                (cix_md := schema.loads(tags))
                and (md := transform.to_comicbox(cix_md))
                and (sub_md := md.get(ROOT_TAG))
            ):
                data.pop(TAGS_KEY, None)
                deep_update(data, sub_md)
                return True
        except Exception as exc:
            LOG.debug(
                f"Failed to parse {schema.__class__.__name__} from keywords in {self._path}: {exc}"
            )
        return False

    def _parse_comma_delimited_tags(self, data):
        tags = data.get(TAGS_KEY)
        tags = StringSetField()._deserialize(tags)  # noqa: SLF001
        data[TAGS_KEY] = tags

    def parse_tags(self, data):
        """Parse different possible keyword schemas."""
        for transform_class in _KEYWORDS_TRANSFORM_CLASSES:
            if self._parse_metadata_from_tags(data, transform_class):
                return data
        self._parse_comma_delimited_tags(data)
        return data

    def unparse_metadata_to_tags(self, data):
        """Stuff comicinfo into keywords."""
        transform = self._transform_class(self._path)
        schema = transform.SCHEMA_CLASS()
        if (md := transform.from_comicbox(data)) and (tags := schema.dumps(md)):
            data[TAGS_KEY] = tags
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_tags,
        aggregate_contributors,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        unparse_metadata_to_tags,
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        disaggregate_contributors,
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
    TRANSFORM_MAP = bidict(
        {
            # AUTHOR_TAG: CONTRIBUTORS_KEY,
            "creator": SCAN_INFO_KEY,  # original document creator
            "keywords": TAGS_KEY,
            "producer": TAGGER_KEY,
            "subject": GENRES_KEY,
            # "title": "title", coded
        }
    )
