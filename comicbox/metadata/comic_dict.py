"""Comic JSON superclass."""
import simplejson as json

from comicbox.metadata.comic_base import ComicBaseMetadata


class ComicDict(ComicBaseMetadata):
    """Request Comic Metadata class."""

    def _from_dict(self, obj):
        raise NotImplementedError()

    def from_dict(self, obj):
        """Parse metadata from a object string."""
        self._from_dict(obj)

    def _to_dict(self):
        """Return metadata as for our JSON object."""
        return self.metadata

    def to_string(self):
        """Return metadata as a JSON string."""
        json_obj = self._to_dict()
        json_str = json.dumps(json_obj)
        return json_str

    def to_file(self, filename):
        """Write metadata to a JSON file."""
        with open(filename, "w") as json_file:
            json_file.write(self.to_string())
