"""Calculate page filenames."""

import re
from contextlib import suppress
from datetime import datetime, timezone
from sys import maxsize

from comicbox.box.archive.init import archive_close
from comicbox.box.archive.mtime import ComicboxArchiveMtime

# ignore dotfiles but not relative ../ leaders.
# ignore macos resource forks
_IGNORE_RE = re.compile(r"(?:^|\/)(?:\.[^\.]|__MACOSX)", re.IGNORECASE)
EPOCH_START = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class ComicboxArchiveFilenames(ComicboxArchiveMtime):
    """Calculate page filenames."""

    def _set_page_filenames(self):
        """Parse the filenames that are comic pages."""
        archive_filenames = self._get_archive_namelist()
        if self._archive_is_pdf:
            self._page_filenames = archive_filenames
        else:
            page_filenames = [
                filename
                for filename in archive_filenames
                if not _IGNORE_RE.search(filename)
                and self.IMAGE_EXT_RE.search(filename)
            ]
            self._page_filenames: tuple[str, ...] | None = tuple(page_filenames)

    def get_page_filenames(self) -> tuple[str, ...]:
        """Get all page filenames."""
        if self._page_filenames is None:
            self._set_page_filenames()
        return self._page_filenames  # pyright: ignore[reportReturnType]

    def get_pagenames_from(self, index_from=None, index_to=None):
        """Return a list of page filenames from the given index onward."""
        page_filenames = ()
        with suppress(IndexError):
            if index_from is None:
                index_from = 0
            if index_to is None:
                index_to = maxsize
            else:
                # Make to index inclusive not exclusive
                index_to += 1
            if page_filenames := self.get_page_filenames():
                return tuple(page_filenames[index_from:index_to])
        return page_filenames

    def get_pagename(self, index):
        """Get the filename of the page by index."""
        pagenames = self.get_pagenames_from(index, index)
        if pagenames:
            return pagenames[0]
        return None

    ##############
    # PAGE COUNT #
    ##############

    def _get_page_count(self):
        page_filenames = self.get_page_filenames()
        return len(page_filenames)

    @archive_close
    def get_page_count(self):
        """Get the page count."""
        if self._page_count is None:
            self._page_count: int | None = self._get_page_count()
        return self._page_count
