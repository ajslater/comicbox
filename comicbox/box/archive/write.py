"""Comicboxs methods for writing to the archive."""

from collections.abc import Mapping
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from loguru import logger

from comicbox.box.archive.archiveinfo import ArchiveInfo
from comicbox.box.archive.read import ComicboxArchiveRead
from comicbox.sources import MetadataSources
from comicbox.zipfile_remove import ZipFileWithRemove

_RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
_CBZ_SUFFIX = ".cbz"
_ALL_ARCHIVE_METADATA_FILENAMES = frozenset(
    {
        fmt.value.filename.lower()
        for fmt in MetadataSources.ARCHIVE_FILE.value.formats
        if fmt.value.enabled
    }
)


class ComicboxArchiveWrite(ComicboxArchiveRead):
    """Comicboxs methods for writing to the archive."""

    def _get_new_archive_path(self):
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ValueError(reason)
        new_path = self._path.with_suffix(_CBZ_SUFFIX)
        if new_path.is_file() and new_path != self._path:
            reason = f"{new_path} already exists."
            raise ValueError(reason)
        return new_path

    def _cleanup_tmp_archive(self, tmp_path, new_path):
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ValueError(reason)
        old_path = self._path
        tmp_path.replace(new_path)
        self._path = new_path
        if old_path.suffix != new_path.suffix:
            logger.info(f"Converted to: {new_path}")
            if self._config.delete_orig and old_path != new_path and new_path.is_file():
                old_path.unlink()
                logger.info(f"Removed: {old_path}")

    def _zipfile_remove_metadata_files(self, zf):
        """Remove metadata files from archive."""
        for path in self._get_archive_namelist():
            fn = Path(path).name.lower()
            if fn in _ALL_ARCHIVE_METADATA_FILENAMES:
                zf.remove(path)

    def _write_archive_metadata_files(self, zf, files):
        # Write metadata files.
        for path, data in files.items():
            compress = (
                ZIP_DEFLATED if self.IMAGE_EXT_RE.search(path) is None else ZIP_STORED
            )
            zf.writestr(
                path,
                data,
                compress_type=compress,
                compresslevel=9,
            )

    @staticmethod
    def _get_filename_from_info(info):
        """Get the filename to write."""
        # Do not write dirs.
        # Prevents empty dirs. Files write implicit parents.
        if ArchiveInfo.is_dir(info):
            return None

        filename = ArchiveInfo.filename(info)

        # Don't copy old metadata files to new archive.
        lower_name = Path(filename).name.lower()
        if lower_name in _ALL_ARCHIVE_METADATA_FILENAMES:
            return None
        return filename

    def _copy_archive_files_to_new_archive(self, zf):
        # copy all files that are *not* metadata files into new archive.
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ValueError(reason)
        infolist = self._get_archive_infolist()
        for info in infolist:
            filename = self._get_filename_from_info(info)
            if not filename:
                continue
            # images usually end up slightly larger with
            # zip compression, so store them.
            compress = (
                ZIP_DEFLATED
                if self.IMAGE_EXT_RE.search(filename) is None
                else ZIP_STORED
            )
            data = self._archive_readfile(filename, to_pixmap=self._archive_is_pdf)
            zf.writestr(
                filename,
                data,
                compress_type=compress,
                compresslevel=9,
            )

    def _patch_zipfile(self, files, comment):
        """In place remove and append to existing zipfile."""
        if not self._path:
            reason = "No zipfile path to write to."
            raise ValueError(reason)
        self.close()
        with ZipFileWithRemove(self._path, "a") as zf:
            self._zipfile_remove_metadata_files(zf)
            self._write_archive_metadata_files(zf, files)
            zf.comment = comment

    def _create_zipfile(self, files: Mapping, comment: bytes):
        """Create new zipfile."""
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ValueError(reason)
        new_path = self._get_new_archive_path()
        tmp_path = self._path.with_suffix(_RECOMPRESS_SUFFIX)
        tmp_path.unlink(missing_ok=True)

        with ZipFile(tmp_path, "x") as zf:
            self._write_archive_metadata_files(zf, files)
            self._copy_archive_files_to_new_archive(zf)
            zf.comment = comment

        # Cleanup
        self.close()
        self._cleanup_tmp_archive(tmp_path, new_path)

    def write_archive_metadata(self, files: Mapping, comment: bytes):
        """Write the metadata files and comment to an archive."""
        if self._archive_is_pdf:
            logger.warning(f"{self._path}: Not writing CBZ metadata to a PDF.")
            return
        if self._archive_cls == ZipFile:
            self._patch_zipfile(files, comment)
        else:
            self._create_zipfile(files, comment)

        # Clear Caches
        old_api_source_data_list = self._sources.get(MetadataSources.API)
        if old_api_source_data_list:
            old_api_source_data = old_api_source_data_list[0]
            old_api_source_metadata = old_api_source_data.data
            old_api_source_format = old_api_source_data.fmt
        else:
            old_api_source_metadata = None
            old_api_source_format = None
        self._reset_archive(old_api_source_format, old_api_source_metadata)

    def write_pdf_metadata(self, mupdf_metadata):
        """Write PDF Metadata."""
        if not self._path:
            reason = "Cannot write pdf metadata without a path."
            raise ValueError(reason)
        archive = self._get_archive()
        if self._archive_is_pdf:
            archive.save_metadata(mupdf_metadata)  # pyright: ignore[reportAttributeAccessIssue]
        else:
            logger.warning(
                f"{self._path}: Not writing pdf metadata dict to a not PDF archive."
            )
