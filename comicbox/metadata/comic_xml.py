"""XML Metadata parser superclass."""
from logging import getLogger
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

from comicbox.metadata.comic_base import ComicBaseMetadata


LOG = getLogger(__name__)


class ComicXml(ComicBaseMetadata):
    """XML Comic Metadata super class."""

    XML_HEADER = '<?xml version="1.0"?>'
    CREDIT_TAGS = {
        "Colorist": set(["colorist", "colourist", "colorer", "colourer"]),
        "CoverArtist": set(
            ["cover", "covers", "coverartist", "cover artist", "coverDesigner"]
        ),
        "Editor": set(["editor"]),
        "Inker": set(["inker", "artist", "finishes"]),
        "Letterer": set(["letterer"]),
        "Penciller": set(["artist", "penciller", "penciler", "breakdowns"]),
        "Writer": set(["writer", "plotter", "scripter", "creator"]),
    }

    ROOT_TAG = ""

    def _get_xml_root(self, tree):
        """Return the xml root."""
        root = tree.getroot()
        if root.tag != self.ROOT_TAG:
            raise ValueError(f"Not a {self.ROOT_TAG} XMLTree")
        return root

    def _from_xml(self, _):
        """Parse metadata from xml."""
        raise NotImplementedError()

    def _to_xml(self):
        """Exxport metadata to xml."""
        raise NotImplementedError()

    def from_string(self, xml_str):
        """Parse an xml string into metadata."""
        try:
            element = ElementTree.fromstring(xml_str)
            tree = ElementTree.ElementTree(element)
            self._from_xml(tree)
        except ParseError as exc:
            LOG.error(f"{self.path} {exc}")

    def from_file(self, filename):
        """Read metadata from a file."""
        tree = ElementTree.parse(filename)
        self._from_xml(tree)

    def to_string(self):
        """Return metadata as an xml string."""
        tree = self._to_xml()
        root = self._get_xml_root(tree)
        tree_str = ElementTree.tostring(root).decode()
        xml_str = self.XML_HEADER + "\n" + tree_str
        return xml_str

    def to_file(self, filename):
        """Write metadata to a file."""
        tree = self._to_xml()
        tree.write(filename, encoding="utf-8")
