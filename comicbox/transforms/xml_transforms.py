"""XML Metadata parser superclass."""

from stringcase import capitalcase

from comicbox.transforms.base import BaseTransform


class XmlTransform(BaseTransform):
    """XML Schema customizations."""

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return capitalcase(data)
