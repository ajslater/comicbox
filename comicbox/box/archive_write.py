"""Comicboxs methods for writing to the archive."""

from collections.abc import Mapping
from logging import getLogger
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from comicbox.box.archive_read import ComicboxArchiveReadMixin
from comicbox.sources import MetadataSources

_RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
_CBZ_SUFFIX = ".cbz"
_ALL_METADATA_NAMES = frozenset(
    {
        source.value.transform_class.SCHEMA_CLASS.FILENAME.lower()
        for source in MetadataSources
    }
)
LOG = getLogger(__name__)


class ComicboxArchiveWriteMixin(ComicboxArchiveReadMixin):
    """Comicboxs methods for writing to the archive."""

    def _ensure_write_archive(self, archive="archive"):
        if not self._archive_cls or not self._path:
            reason = f"Cannot write {archive} metadata without and archive path."
            raise ValueError(reason)

    def _get_new_archive_path(self):
        self._ensure_write_archive()
        new_path = self._path.with_suffix(_CBZ_SUFFIX)  # type: ignore
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
            LOG.info(f"Converted to: {new_path}")
            if self._config.delete_orig and old_path != new_path and new_path.is_file():
                old_path.unlink()
                LOG.info(f"Removed: {old_path}")

    def _is_rewrite(self):
        # Determine if we need to to do a rewrite or can append.
        rewrite = False
        if self._archive_cls != ZipFile:
            rewrite = True
        else:
            namelist = self._get_archive_namelist()
            for filename in namelist:
                if Path(filename).name.lower() in _ALL_METADATA_NAMES:
                    rewrite = True
                    break
        return rewrite

    @staticmethod
    def _write_archive_metadata_files(zf, files):
        for filename, data in files.items():
            zf.writestr(
                filename,
                data,
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )

    def _copy_archive_files_to_new_archive(self, zf):
        # copy all files that are *not* metadata files into new archive.
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ValueError(reason)
        infolist = self._get_archive_infolist()
        for info in infolist:
            try:
                if info.is_dir():  # type: ignore
                    continue
            except AttributeError:
                if info.isdir():  # type: ignore
                    continue
            try:
                filename = info.filename  # type: ignore
            except AttributeError:
                filename = info.name  # type: ignore
            if Path(filename).name.lower() in _ALL_METADATA_NAMES:
                # remove all metadata files from new archive.
                continue

            # images usually end up slightly larger with
            # zip compression, so store them.
            compress = (
                ZIP_DEFLATED
                if self.IMAGE_EXT_RE.search(filename) is None
                else ZIP_STORED
            )
            zf.writestr(
                filename,
                self._archive_readfile(filename, True),
                compress_type=compress,
                compresslevel=9,
            )

    def _rewrite_archive(self, files: Mapping, comment: bytes):
        """CREATE NEW ARCHIVE."""
        self._ensure_write_archive()
        new_path = self._get_new_archive_path()
        tmp_path = self._path.with_suffix(_RECOMPRESS_SUFFIX)  # type: ignore
        tmp_path.unlink(missing_ok=True)

        with ZipFile(tmp_path, "x") as zf:
            self._write_archive_metadata_files(zf, files)
            self._copy_archive_files_to_new_archive(zf)
            zf.comment = comment

        # Cleanup
        self.close()
        self._cleanup_tmp_archive(tmp_path, new_path)

    def _append_archive(self, files, comment):
        """APPEND TO EXISTING ARCHIVE."""
        self._ensure_write_archive()
        self.close()
        with ZipFile(self._path, "a") as zf:  # type: ignore
            self._write_archive_metadata_files(zf, files)
            zf.comment = comment

    def write_archive_metadata(self, files: Mapping, comment: bytes):
        """Write the metadata files and comment to an archive."""
        self._ensure_write_archive()
        if self._archive_is_pdf:
            LOG.warning(f"{self._path}: Not writing CBZ metadata to a PDF.")
            return

        if self._is_rewrite():
            self._rewrite_archive(files, comment)
        else:
            self._append_archive(files, comment)

        # Clear Caches
        old_api_source_data_list = self._sources.get(MetadataSources.API)
        if old_api_source_data_list and old_api_source_data_list[0]:
            old_api_source_metadata = old_api_source_data_list[0].metadata
        else:
            old_api_source_metadata = None
        self._reset_archive(old_api_source_metadata)

    #########################
    # SPECIAL ARCHIVE WRITE #
    #########################

    def write_pdf_metadata(self, mupdf_metadata):
        """Write PDF Metadata."""
        self._ensure_write_archive("pdf")
        archive = self._get_archive()
        if self._archive_is_pdf:
            archive.save_metadata(mupdf_metadata)  # type: ignore
        else:
            LOG.warning(
                f"{self._path}: Not writing pdf metadata dict to a not PDF archive."
            )
