"""Mimic comicbox.ComicArchive functions for PDFs."""
from logging import getLogger
from xml.etree.ElementTree import Element, ElementTree, SubElement

from comicbox.metadata.comic_xml import ComicXml

LOG = getLogger(__name__)


class PDFParser(ComicXml):
    """PDF class."""

    ROOT_TAG = "x:xmpmeta"
    CONFIG_KEYS = frozenset(["pdf"])
    _KEY_MAP = {
        "name": "title",
        "credits": "author",
        "scan_info": "creator",
    }
    _M2M_KEY_MAP = {
        "tags": "keywords",
        "genres": "subject",
    }
    KEY_MAP = {**_KEY_MAP, **_M2M_KEY_MAP}
    FILENAME = "pdf-metadata.xml"

    def _parse_creator(self, role, value):
        credit_dict = {
            "role": role,
            "person": value,
        }
        if not credit_dict:
            return None
        credit_list = self.metadata.get("credits", [])
        credit_list.append(credit_dict)
        return credit_list

    def _parse_tag(self, comicbox_key, value):
        if comicbox_key == "credits":
            value = self._parse_creator("writer", value)
        return value

    def from_dict(self, pdf_md):
        """Get metadata from pdf format."""
        for comicbox_key, pdf_key in self._KEY_MAP.items():
            value = pdf_md.get(pdf_key)
            value = self._parse_tag(comicbox_key, value)
            if self.is_number_or_truthy(value):
                self.metadata[comicbox_key] = value
        for comicbox_key, pdf_key in self._M2M_KEY_MAP.items():
            value = pdf_md.get(pdf_key)
            if tags := self.parse_str_set(value):
                self.metadata[comicbox_key] = tags
        return self.metadata

    def _to_dict_author(self):
        value = None
        credit_list = self.metadata.get("credits", [])
        for credit_dict in credit_list:
            if credit_dict.get("role") == "writer":
                value = credit_dict.get("person")
                break
        return value

    def _serialize_tag(self, pdf_key, comicbox_key):
        if pdf_key == "author":
            value = self._to_dict_author()
        else:
            value = self.metadata.get(comicbox_key)
        return value

    def _serialize_m2m_tag(self, comicbox_key):
        values = self.metadata.get(comicbox_key)
        if not values:
            return ""
        return self.serialize_str_set(values)

    def to_dict(self):
        """Map comicbox metadata to pdf format."""
        pdf_md = {}
        for comicbox_key, pdf_key in self._KEY_MAP.items():
            value = self._serialize_tag(pdf_key, comicbox_key)
            if self.is_number_or_truthy(value):
                pdf_md[pdf_key] = value
        for comicbox_key, pdf_key in self._M2M_KEY_MAP.items():
            value = self._serialize_m2m_tag(comicbox_key)
            if self.is_number_or_truthy(value):
                pdf_md[pdf_key] = value
        return pdf_md

    def _to_xml_root(self):
        """Create a pdf xml document."""
        root = Element(self.ROOT_TAG)
        root.attrib["xmlns:x"] = "adobe:ns:meta/"
        root.attrib[
            "x:xmptk"
        ] = "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21"
        rdf_root = SubElement(root, "rdf:RDF")
        rdf_root.attrib["xmlns:rdf"] = "http://www.w3.org/1999/02/22-rdf-syntax-ns"
        rdf_desc = SubElement(rdf_root, "rdf:Description")
        rdf_desc.attrib["xmlns:pdf"] = "http://ns.adobe.com/pdf/1.3/"
        return root, rdf_desc

    def _get_pdf_xml_tag(self, key):
        """Transform from mupdf to PDF xml tag."""
        return "pdf:" + key.capitalize()

    def _to_xml(self):
        """Export to pdf xml."""
        root, rdf_desc = self._to_xml_root()
        for key, value in self.metadata.items():
            pdf_key = self.KEY_MAP.get(key)
            if not pdf_key:
                continue
            xml_tag = self._get_pdf_xml_tag(pdf_key)
            if key in self._M2M_KEY_MAP:
                text = self._serialize_m2m_tag(value)
            else:
                text = self._serialize_tag(pdf_key, value)
            SubElement(rdf_desc, xml_tag).text = text

        return ElementTree(root)

    def _from_xml(self, tree):
        """Read from any xml."""
        root = self._get_xml_root(tree)
        for pdf_tag, comicbox_tag in self.KEY_MAP.items():
            xml_tag = self._get_pdf_xml_tag(pdf_tag)
            element = root.find(xml_tag)
            if element is None or element.text is None:
                continue
            val = element.text.strip()
            if not val:
                continue
            if comicbox_tag in self._M2M_KEY_MAP:
                value = self.parse_str_set(val)
            else:
                value = self._parse_tag(comicbox_tag, val)
            if not self.is_number_or_truthy(value):
                continue
            self.metadata[comicbox_tag] = value
