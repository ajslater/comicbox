"""Calculate page filenames."""

import re
from sys import maxsize

from comicbox.box.archive import archive_close
from comicbox.box.archive_read import ComicboxArchiveReadMixin

# ignore dotfiles but not relative ../ leaders.
# ignore macos resource forks
_IGNORE_RE = re.compile(r"(?:^|\/)(?:\.[^\.]|__MACOSX)", re.IGNORECASE)


class ComicboxPageFilenamesMixin(ComicboxArchiveReadMixin):
    """Calculate page filenames."""

    ##################
    # PAGE FILENAMES #
    ##################

    def _set_page_filenames(self):
        """Parse the filenames that are comic pages."""
        archive_filenames = self._get_archive_namelist()
        if self._archive_is_pdf:
            self._page_filenames = archive_filenames
        else:
            self._page_filenames = []
            for filename in archive_filenames:
                if not _IGNORE_RE.search(filename) and self.IMAGE_EXT_RE.search(
                    filename
                ):
                    self._page_filenames.append(filename)

    def get_page_filenames(self):
        """Get all page filenames."""
        if not self._page_filenames:
            self._set_page_filenames()
        return self._page_filenames

    def get_pagenames_from(self, index_from=None, index_to=None):
        """Return a list of page filenames from the given index onward."""
        try:
            if index_from is None:
                index_from = 0
            if index_to is None:
                index_to = maxsize
            else:
                # Make to index inclusive not exclusive
                index_to += 1
            page_filenames = self.get_page_filenames()
            return tuple(page_filenames[index_from:index_to])
        except IndexError:
            return None

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
            self._page_count = self._get_page_count()
        return self._page_count
