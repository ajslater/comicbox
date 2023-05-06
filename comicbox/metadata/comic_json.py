"""Comic JSON superclass."""
import json
from logging import getLogger
from pathlib import Path

from comicbox.metadata.comic_base import ComicBaseMetadata

LOG = getLogger(__name__)


class ComicJSON(ComicBaseMetadata):
    """JSON Comic Metadata class."""

    def _from_json(self, _):
        """Get metadata from json."""
        raise NotImplementedError

    def _to_json(self):
        """Write metadata from to json."""
        raise NotImplementedError

    def from_string(self, json_str):
        """Parse metadata from a JSON string."""
        try:
            json_str = json_str.strip()
            if not json_str:
                return
            json_obj = json.loads(json_str)
            self._from_json(json_obj)
        except json.JSONDecodeError as exc:
            LOG.warning(f"{self.path} {type(exc).__name__} {exc}")

    def from_file(self, filename):
        """Parse metadata from a JSON file."""
        with Path(filename).open("r") as json_file:
            self.from_string(json_file.read())

    def to_string(self):
        """Return metadata as a JSON string."""
        json_obj = self._to_json()
        return json.dumps(json_obj)

    def to_file(self, filename):
        """Write metadata to a JSON file."""
        with Path(filename).open("w") as json_file:
            json_file.write(self.to_string())
