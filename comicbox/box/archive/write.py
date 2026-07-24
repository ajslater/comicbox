"""Comicboxs methods for writing to the archive."""

from collections.abc import Mapping
from pathlib import Path

from loguru import logger
from zipremove import ZIP_DEFLATED, ZIP_STORED, ZipFile

from comicbox._pdf import PAGE_FORMAT_PIXMAP_JPEG
from comicbox.box.archive.archiveinfo import ArchiveInfo, InfoType
from comicbox.box.archive.read import ComicboxArchiveRead
from comicbox.exceptions import ArchiveWriteError
from comicbox.formats.sources import MetadataSources

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

    def _get_new_archive_path(self) -> Path:
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ArchiveWriteError(reason)
        new_path = self._path.with_suffix(_CBZ_SUFFIX)
        if new_path.is_file() and new_path != self._path:
            reason = f"{new_path} already exists."
            raise ArchiveWriteError(reason)
        return new_path

    def _cleanup_tmp_archive(self, tmp_path: Path, new_path: Path) -> None:
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ArchiveWriteError(reason)
        old_path = self._path
        tmp_path.replace(new_path)
        self._path: Path | None = new_path
        if old_path.suffix != new_path.suffix:
            logger.info(f"Converted to: {new_path}")
            if (
                self._config.general.delete_orig
                and old_path != new_path
                and new_path.is_file()
            ):
                old_path.unlink()
                logger.info(f"Removed: {old_path}")

    def _archive_remove_metadata_files(self, zf: ZipFile) -> None:
        """Remove metadata files from archive."""
        for path in self.namelist():
            fn = Path(path).name.lower()
            if fn in _ALL_ARCHIVE_METADATA_FILENAMES:
                # zipremove patches remove()/repack() onto the stdlib
                # ZipFile on Python < 3.14 (3.14 has them natively), so
                # the 3.10 typeshed stubs can't see either method.
                zf.remove(path)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]
        zf.repack()  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]

    def _archive_write_metadata_files(
        self, zf: ZipFile, files: Mapping[str, bytes]
    ) -> None:
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
    def _get_filename_from_info(info: InfoType) -> str | None:
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

    @staticmethod
    def _ensure_image_suffix(filename: str, props: dict[str, str] | None) -> str:
        entry_path = Path(filename)
        suffix = entry_path.suffix
        if not suffix:
            ext = props.get("ext", "jpg") if props else "jpg"
            suffix = "." + ext
            filename += suffix
        return filename

    def _copy_archive_files_to_new_archive(self, zf: ZipFile) -> None:
        # copy all files that are *not* metadata files into new archive.
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ArchiveWriteError(reason)
        infolist = self.infolist()
        for info in infolist:
            filename = self._get_filename_from_info(info)
            if not filename:
                continue
            # Default pdf pages to whole-page jpegs: comic readers (and
            # comicbox's own page regex) don't recognize raw pixmap ppm
            # data, and the page render applies pdf display rotation.
            pdf_format = self._get_pdf_format(default=PAGE_FORMAT_PIXMAP_JPEG)
            props = {}
            data = self._archive_readfile(filename, pdf_format=pdf_format, props=props)
            filename = self._ensure_image_suffix(filename, props)
            # images usually end up slightly larger with zip compression,
            # so store them. Decide from the final name — pdf pages only
            # gain their image suffix above.
            compress = (
                ZIP_DEFLATED
                if self.IMAGE_EXT_RE.search(filename) is None
                else ZIP_STORED
            )
            zf.writestr(
                filename,
                data,
                compress_type=compress,
                compresslevel=9,
            )

    def _patch_zipfile(self, files: Mapping[str, bytes], comment: bytes) -> None:
        """In place remove and append to existing zipfile."""
        if not self._path:
            reason = "No zipfile path to write to."
            raise ArchiveWriteError(reason)
        self.close()
        with ZipFile(self._path, "a") as zf:
            self._archive_remove_metadata_files(zf)
            self._archive_write_metadata_files(zf, files)
            zf.comment = comment

    def _create_zipfile(self, files: Mapping, comment: bytes) -> None:
        """Create new zipfile."""
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ArchiveWriteError(reason)
        new_path = self._get_new_archive_path()
        tmp_path = self._path.with_suffix(_RECOMPRESS_SUFFIX)
        tmp_path.unlink(missing_ok=True)
        logger.info(f"Creating {new_path}...")
        with ZipFile(tmp_path, "x") as zf:
            self._archive_write_metadata_files(zf, files)
            self._copy_archive_files_to_new_archive(zf)
            zf.comment = comment

        # Cleanup
        self.close()
        self._cleanup_tmp_archive(tmp_path, new_path)

    def _update_pdffile(self, files: Mapping, mupdf_metadata: Mapping) -> None:
        if not self._path:
            reason = "No pdfile path to write to."
            raise ArchiveWriteError(reason)
        if not self._archive_cls:
            reason = "PDF archive class not initialized."
            raise ArchiveWriteError(reason)
        self.close()
        delete_all_tags = self._config.write.delete_all_tags
        with self._archive_cls(self._path) as pf:
            if delete_all_tags or mupdf_metadata:
                pf.write_metadata(mupdf_metadata)
            if delete_all_tags or files:
                self._archive_remove_metadata_files(pf)
                self._archive_write_metadata_files(pf, files)

    def write_archive_metadata(
        self, files: Mapping, comment: bytes, mupdf_metadata: Mapping
    ) -> None:
        """
        Write the metadata files and comment to an archive.

        Pure file I/O: cache invalidation after the rewrite is the dump
        layer's job (ComicboxDump._reset_caches_after_write).
        """
        if self._archive_cls == ZipFile:
            self._patch_zipfile(files, comment)
        elif self._archive_is_pdf and not self._config.convert.cbz:
            self._update_pdffile(files, mupdf_metadata)
        else:
            self._create_zipfile(files, comment)
