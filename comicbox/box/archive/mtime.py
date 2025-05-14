"""Calculate page filenames."""

import re
from datetime import datetime, timezone
from pathlib import Path

from comicbox.box.archive.archiveinfo import ArchiveInfo
from comicbox.box.archive.init import archive_close
from comicbox.box.archive.write import ComicboxArchiveWrite
from comicbox.sources import MetadataSources

# ignore dotfiles but not relative ../ leaders.
# ignore macos resource forks
_IGNORE_RE = re.compile(r"(?:^|\/)(?:\.[^\.]|__MACOSX)", re.IGNORECASE)
EPOCH_START = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class ComicboxArchiveMtime(ComicboxArchiveWrite):
    """Calculate page filenames."""

    def _get_metadata_files_mtime(self):
        """Get the latest metadata archive file mtime according to the read config."""
        formats = frozenset(
            frozenset(MetadataSources.ARCHIVE_FILENAME.value.formats)
            & self._config.read
        )
        metadata_lower_filenames = frozenset(fmt.filename.lower() for fmt in formats)

        max_mtime = EPOCH_START
        infolist = self._get_archive_infolist()
        for info in infolist:
            if ArchiveInfo.is_dir(info):
                continue

            filename = ArchiveInfo.filename(info)
            if not filename:
                continue
            path = Path(filename)
            if path.name.lower() not in metadata_lower_filenames:
                continue

            mtime = ArchiveInfo.datetime(info)
            if not mtime:
                return self._path and self._path.stat().st_mtime
            max_mtime = max(max_mtime, mtime)
        return max_mtime

    @archive_close
    def get_metadata_files_mtime(self):
        """Get the latest metadata archive file mtime according to the read config."""
        return self._get_metadata_files_mtime()

    @archive_close
    def get_metadata_mtime(self):
        """Get the latest metadata mtime according to the read config."""
        # Ensure the archive is ready.
        archive = self._get_archive()

        if self._archive_is_pdf:
            return self._path and self._path.stat().st_mtime

        if MetadataSources.ARCHIVE_COMMENT.value.formats & self._config.read:
            comment = getattr(archive, "comment", b"")
            if comment.startswith(b"{"):
                return self._path and self._path.stat().st_mtime

        return self._get_metadata_files_mtime()
