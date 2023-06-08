"""Mimic comicbox.ComicArchive functions for PDFs."""
from logging import getLogger

from comicbox.metadata.comic_base import ComicBaseMetadata

LOG = getLogger(__name__)


class PDFParser(ComicBaseMetadata):
    """PDF class."""

    CONFIG_KEYS = frozenset(["pdf"])
    _KEY_MAP = {
        "name": "title",
        "writer": "author",
        "scan_info": "creator",
    }
    _M2M_KEY_MAP = {
        "tags": "keywords",
        "genres": "subject",
    }

    def _from_dict_creator(self, comicbox_key, value):
        if "creators" not in self.metadata:
            self.metadata["creators"] = []
        creator = {
            "role": comicbox_key,
            "person": value,
        }
        self.metadata["creators"].append(creator)

    def _from_dict_key(self, pdf_md, comicbox_key, pdf_key):
        value = pdf_md.get(pdf_key)
        if not value:
            return
        if comicbox_key == "writer":
            self._from_dict_creator(comicbox_key, value)
        else:
            self.metadata[comicbox_key] = value

    def _from_dict_m2m_key(self, pdf_md, comicbox_key, pdf_key):
        value = pdf_md.get(pdf_key)
        if not value:
            return
        tags = value.split(",;")
        stripped_tags = []
        for tag in tags:
            stripped_tag = tag.strip()
            if stripped_tag:
                stripped_tags.append(stripped_tag)

        self.metadata[comicbox_key] = stripped_tags

    def from_dict(self, pdf_md):
        """Get metadata from pdf format."""
        for comicbox_key, pdf_key in self._KEY_MAP.items():
            self._from_dict_key(pdf_md, comicbox_key, pdf_key)
        for comicbox_key, pdf_key in self._M2M_KEY_MAP.items():
            self._from_dict_m2m_key(pdf_md, comicbox_key, pdf_key)
        return self.metadata

    def _to_dict_author(self):
        value = None
        creators = self.metadata.get("creators", [])
        for creator in creators:
            if creator.get("role") == "writer":
                value = creator.get("person")
                break
        return value

    def _to_dict_key(self, pdf_md, pdf_key, comicbox_key):
        if pdf_key == "author":
            value = self._to_dict_author()
        else:
            value = self.metadata.get(comicbox_key)

        if value:
            pdf_md[pdf_key] = value

    def _to_dict_m2m_key(self, pdf_md, pdf_key, comicbox_key):
        values = self.metadata.get(comicbox_key)
        if not values:
            return
        tag_str = ",".join(values)
        pdf_md[pdf_key] = tag_str

    def to_dict(self):
        """Map comicbox metadata to pdf format."""
        pdf_md = {}
        for comicbox_key, pdf_key in self._KEY_MAP.items():
            self._to_dict_key(pdf_md, pdf_key, comicbox_key)
        for comicbox_key, pdf_key in self._M2M_KEY_MAP.items():
            self._to_dict_m2m_key(pdf_md, pdf_key, comicbox_key)
        return pdf_md
