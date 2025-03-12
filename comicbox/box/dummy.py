"""A dummy PDFFile to help with typing."""


class PDFFile:
    """Empty."""

    def read(self):
        """Empty."""
        return b""

    def namelist(self):
        """Empty."""
        return []

    def infolist(self):
        """Empty."""
        return []

    def close(self):
        """Noop."""

    def get_metadata(self):
        """Empty."""
        return {}
