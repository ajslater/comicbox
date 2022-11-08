"""XML Metadata parser superclass."""
from logging import getLogger
from xml.etree import ElementTree

from defusedxml.ElementTree import ParseError, fromstring, parse

from comicbox.metadata.comic_base import ComicBaseMetadata


LOG = getLogger(__name__)


class ComicXml(ComicBaseMetadata):
    """XML Comic Metadata super class."""

    XML_HEADER = '<?xml version="1.0"?>'
    CREDIT_TAGS = {
        "Colorist": frozenset(["colorist", "colourist", "colorer", "colourer"]),
        "CoverArtist": frozenset(
            ["cover", "covers", "coverartist", "cover artist", "coverDesigner"]
        ),
        "Editor": frozenset(["editor"]),
        "Inker": frozenset(["inker", "artist", "finishes"]),
        "Letterer": frozenset(["letterer"]),
        "Penciller": frozenset(["artist", "penciller", "penciler", "breakdowns"]),
        "Writer": frozenset(["writer", "author", "plotter", "scripter", "creator"]),
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
        """Export metadata to xml."""
        raise NotImplementedError()

    def from_string(self, xml_str):
        """Parse an xml string into metadata."""
        # Use defusedxml for safety.
        try:
            element = fromstring(xml_str)
            tree = ElementTree.ElementTree(element)
            self._from_xml(tree)
        except ParseError as exc:
            LOG.error(f"{self.path} {type(exc).__name__} {exc}")

    def from_file(self, filename):
        """Read metadata from a file."""
        tree = parse(filename)
        self._from_xml(tree)

    def to_string(self):
        """Return metadata as an xml string."""
        tree = self._to_xml()
        root = self._get_xml_root(tree)
        tree_str = ElementTree.tostring(root).decode(errors="replace")
        xml_str = self.XML_HEADER + "\n" + tree_str
        return xml_str

    def to_file(self, filename):
        """Write metadata to a file."""
        tree = self._to_xml()
        tree.write(filename, encoding="utf-8")
