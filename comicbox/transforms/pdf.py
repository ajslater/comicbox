"""Mimic comicbox.Comicbox functions for PDFs."""
from collections.abc import Mapping

from bidict import bidict

from comicbox.schemas.comicbox_mixin import (
    CONTRIBUTORS_KEY,
    GENRES_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    ISSUE_KEY,
    PUBLISHER_KEY,
    SCAN_INFO_KEY,
    SERIES_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    VOLUME_KEY,
    WRITER_KEY,
)
from comicbox.schemas.identifier import NSS_KEY
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.transforms.identifiers import to_urn_string
from comicbox.transforms.xml import XmlTransform


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

    def parse_groups_from_tags(self, data):
        """Parse groups from tags."""
        tags = data.get(TAGS_KEY)
        if not tags:
            return data
        processed_tags = set()
        for tag in tags:
            parts = tag.split(self.GROUP_TAG_DELIMETER, 1)
            key = parts[0].lower()
            if key not in self.GROUP_KEYS:
                processed_tags.add(tag)
                continue
            data[key] = parts[1]
        data[TAGS_KEY] = processed_tags
        return data

    def unparse_identifiers_into_tags(self, data):
        """Write identifiers to keywords only for PDF."""
        identifiers = data.pop(IDENTIFIERS_KEY, None)
        if not identifiers:
            return data
        new_tags = set()
        for nid, identifier in identifiers.items():
            nss = identifier.get(NSS_KEY)
            identifier_tag = to_urn_string(nid, nss)
            new_tags.add(identifier_tag)
        if not new_tags:
            return data
        data[TAGS_KEY] = new_tags | data.get(TAGS_KEY, set())
        return data

    def unparse_groups_into_tags(self, data):
        """Write groups into keywords."""
        new_tags = set()
        for group_key in self.GROUP_KEYS:
            value = data.pop(group_key, None)
            if isinstance(value, Mapping):
                value = value.get("name")
            if not value:
                continue
            keyword = self.GROUP_TAG_DELIMETER.join((group_key, str(value)))
            new_tags.add(keyword)
        if not new_tags:
            return data
        data[TAGS_KEY] = new_tags | data.get(TAGS_KEY, set())
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_groups_from_tags,
        aggregate_contributors,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        unparse_identifiers_into_tags,
        unparse_groups_into_tags,
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
