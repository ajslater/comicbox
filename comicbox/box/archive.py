"""Comicbox methods on the archive itself."""

import re
from functools import wraps
from logging import getLogger

from comicbox.box.init import ComicboxInitMixin

LOG = getLogger(__name__)


def archive_close(fn):
    """Auto close the archive."""

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        if self._config.close_fd:
            self.close()
        return result

    return wrapper


class ComicboxArchiveMixin(ComicboxInitMixin):
    """Methods on the archive itself."""

    IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)$", re.IGNORECASE)

    def __enter__(self):
        """Context enter."""
        self._config.close_fd = False
        return self

    def __exit__(self, *_exc):
        """Context close."""
        self.close()

    def close(self):
        """Close the open archive."""
        try:
            if self._archive and hasattr(self._archive, "close"):
                self._archive.close()
        except Exception as exc:
            LOG.warning(f"closing archive {self._path}: {exc}")
        finally:
            self._archive = None

    def _get_archive(self):
        """Set archive instance open for reading."""
        if not self._archive and self._archive_cls:
            self._archive = self._archive_cls(self._path)
        return self._archive
