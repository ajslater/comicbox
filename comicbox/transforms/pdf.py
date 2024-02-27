"""Mimic comicbox.Comicbox functions for PDFs."""

from logging import getLogger
from xml.sax.saxutils import unescape

from bidict import bidict

from comicbox.dict_funcs import deep_update
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
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.xml import XmlTransform

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

    def parse_comicinfo_from_tags(self, data):
        """Parse comicinfo from keywords."""
        tags = data.get(TAGS_KEY)
        transform = ComicInfoTransform()
        schema = transform.SCHEMA_CLASS()
        try:
            tags = unescape(tags)
            if (
                (cix_md := schema.loads(tags))
                and (md := transform.to_comicbox(cix_md))
                and (sub_md := md.get(ROOT_TAG))
            ):
                data.pop(TAGS_KEY, None)
                deep_update(data, sub_md)
        except Exception as exc:
            LOG.debug(
                f"Failed to parse {schema.__class__.__name__} from keywords in {self._path}: {exc}"
            )

        return data

    def unparse_comicinfo_to_tags(self, data):
        """Stuff comicinfo into keywords."""
        transform = ComicInfoTransform()
        schema = transform.SCHEMA_CLASS()
        if (md := transform.from_comicbox(data)) and (tags := schema.dumps(md)):
            data[TAGS_KEY] = tags
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        aggregate_contributors,
        parse_comicinfo_from_tags,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        unparse_comicinfo_to_tags,
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        disaggregate_contributors,
    )


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
            # "title": "title",
        }
    )
