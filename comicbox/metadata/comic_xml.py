"""XML Metadata parser superclass."""
from logging import getLogger
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree

from defusedxml.ElementTree import ParseError, fromstring, parse

from comicbox.metadata.comic_base import ComicBaseMetadata

LOG = getLogger(__name__)


class ComicXml(ComicBaseMetadata):
    """XML Comic Metadata super class."""

    ROOT_TAG = ""

    def _get_xml_root(self, tree):
        """Return the xml root."""
        root = tree.getroot()
        if root.tag != self.ROOT_TAG:
            reason = f"Not a {self.ROOT_TAG} XMLTree"
            raise ValueError(reason)
        return root

    def _from_xml(self, _):
        """Parse metadata from xml."""
        raise NotImplementedError

    def _to_xml(self):
        """Export metadata to xml."""
        raise NotImplementedError

    def from_string(self, xml_str):
        """Parse an xml string into metadata."""
        # Use defusedxml for safety.
        try:
            element = fromstring(xml_str)
            tree = ElementTree.ElementTree(element)
            self._from_xml(tree)
        except ParseError as exc:
            LOG.warning(f"{self.path} {type(exc).__name__} {exc}")

    def from_file(self, filename):
        """Read metadata from a file."""
        tree = parse(filename)
        self._from_xml(tree)

    def to_string(self):
        """Return metadata as an xml string."""
        tree = self._to_xml()
        root = self._get_xml_root(tree)
        tree_str = ElementTree.tostring(root, encoding="utf-8").decode(errors="replace")
        dom = minidom.parseString(tree_str)  # noqa: S318
        pretty_xml_bytes = dom.toprettyxml(
            indent="  ", encoding="utf-8", standalone=True
        )
        return pretty_xml_bytes.decode(errors="replace")

    def to_file(self, filename):
        """Write metadata to a file."""
        xml_str = self.to_string()
        with Path(filename).open("w") as f:
            f.write(xml_str)
