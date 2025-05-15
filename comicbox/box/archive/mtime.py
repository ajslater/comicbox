"""Calculate page filenames."""

from datetime import datetime, timezone
from pathlib import Path

from comicbox.box.archive.archiveinfo import ArchiveInfo
from comicbox.box.archive.init import archive_close
from comicbox.box.archive.write import ComicboxArchiveWrite

_BRACKETS = ("{", b"{")


class ComicboxArchiveMtime(ComicboxArchiveWrite):
    """Calculate page filenames."""

    def _is_comment_json(self, archive):
        return (
            self._config.computed.is_read_comments
            and (comment := getattr(archive, "comment", ""))
            and (comment[0] in _BRACKETS)
        )

    def get_path_mtime_dttm(self) -> datetime | None:
        """Get the path mtime as datetime."""
        if not self._path_mtime_dttm and self._path:
            self._path_mtime_dttm: datetime | None = datetime.fromtimestamp(
                self._path.stat().st_mtime, tz=timezone.utc
            )
        return self._path_mtime_dttm

    def _get_metadata_files_mtime(self) -> datetime | None:
        """Get the latest metadata archive file mtime according to the read config."""
        max_mtime: None | datetime = None
        infolist = self._get_archive_infolist()
        for info in infolist:
            if ArchiveInfo.is_dir(info):
                continue

            # filename
            filename = ArchiveInfo.filename(info)
            if not filename:
                continue
            path = Path(filename)
            if (
                path.name.lower()
                not in self._config.computed.read_metadata_lower_filenames
            ):
                continue

            # mtime
            mtime = ArchiveInfo.datetime(info)
            if not mtime:
                mtime = self.get_path_mtime_dttm()
            if mtime and (max_mtime is None or (max_mtime < mtime)):
                max_mtime = mtime
        return max_mtime

    @archive_close
    def get_metadata_files_mtime(self) -> datetime | None:
        """Get the latest metadata archive file mtime according to the read config."""
        return self._get_metadata_files_mtime()

    @archive_close
    def get_metadata_mtime(self) -> datetime | None:
        """Get the latest metadata mtime according to the read config."""
        # Ensure the archive is ready.
        archive = self._get_archive()

        if self._archive_is_pdf or self._is_comment_json(archive):
            return self.get_path_mtime_dttm()

        return self._get_metadata_files_mtime()
