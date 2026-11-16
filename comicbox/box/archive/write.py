"""Comicboxs methods for writing to the archive."""

from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from types import MappingProxyType
from typing import Any, TypeAlias

from loguru import logger
from zipremove import ZIP_DEFLATED, ZIP_STORED, ZipFile

from comicbox._pdf import PAGE_FORMAT_PIXMAP_JPEG
from comicbox.box.archive.archiveinfo import ArchiveInfo, InfoType
from comicbox.box.archive.read import ComicboxArchiveRead
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import (
    ArchiveWriteError,
    DestinationOccupiedError,
    UnsupportedArchiveTypeError,
)
from comicbox.formats.sources import MetadataSources

FileKey: TypeAlias = tuple[int, int] | Path

_RECOMPRESS_SUFFIX = ".comicbox_tmp_zip"
_CBZ_SUFFIX = ".cbz"
# What a sniffed archive really is, for a message about one misnamed.
_ARCHIVE_KINDS = MappingProxyType(
    {FileTypeEnum.CBR: "RAR", FileTypeEnum.CB7: "7z", FileTypeEnum.CBT: "tar"}
)
# Destinations a conversion is currently writing to. Archives differing
# only by suffix ("Foo.cbr" and "Foo.cbt", a common way for a library to
# carry one issue twice) both convert to "Foo.cbz", and bulk writes run on
# a thread pool: without this the second writer replaces the first's
# finished file and, under ``delete_orig``, both originals are unlinked —
# one archive's contents gone for good. Claiming the destination turns the
# loser into an ordinary per-file error instead. Each claim is held under
# the path it was taken by, mapped to the file that path named then.
_INFLIGHT_DESTINATIONS: dict[Path, FileKey] = {}
_INFLIGHT_GUARD = Lock()


def file_key(path: Path) -> FileKey:
    """
    Name the file a path points at, so two spellings of one file agree.

    An existing file is its device and inode, which a symlink, a hard link
    and the other case of its name on a case-insensitive disk all share.
    A path with nothing there yet, such as a conversion's destination, is
    its resolved spelling, which still sees through a linked directory.
    """
    try:
        stat = path.stat()
    except OSError:
        return path.resolve()
    return (stat.st_dev, stat.st_ino)


def _claim_destination(destination: Path, source: Path) -> None:
    """
    Take a write destination, refusing one already in flight.

    The claim is on the file, not the spelling: ``lib/link.cbz``, a link to
    ``cw1.cbz``, is refused while ``cw1.cbz`` is being written.
    """
    key = file_key(destination)
    with _INFLIGHT_GUARD:
        if destination in _INFLIGHT_DESTINATIONS or (
            key in _INFLIGHT_DESTINATIONS.values()
        ):
            raise DestinationOccupiedError(source, destination, "inflight")
        _INFLIGHT_DESTINATIONS[destination] = key


def _release_destination(path: Path) -> None:
    """
    Release a claimed destination by the path that claimed it.

    Not by its file key: a conversion's destination is a new file by the
    time it is released, so its key has changed since the claim.
    """
    with _INFLIGHT_GUARD:
        _INFLIGHT_DESTINATIONS.pop(path, None)


ALL_ARCHIVE_METADATA_FILENAMES = frozenset(
    {
        fmt.value.filename.lower()
        for fmt in MetadataSources.ARCHIVE_FILE.value.formats
        if fmt.value.enabled
    }
)


def _same_path(one: Path, other: Path) -> bool:
    """Tell whether two paths name one file, as on a case-insensitive disk."""
    if one == other:
        return True
    try:
        return one.samefile(other)
    except OSError:
        return False


class ComicboxArchiveWrite(ComicboxArchiveRead):
    """Comicboxs methods for writing to the archive."""

    def get_write_destination(self) -> Path:
        """
        Where a write of this archive lands: in place, or the CBZ it repacks to.

        Decided from the sniffed archive type (``_archive_cls`` /
        ``_archive_is_pdf``) and ``convert.cbz`` -- never from the suffix. A
        zip is rewritten in place whatever it is called; a PDF is updated in
        place unless ``convert.cbz`` asks for a repack; everything else
        (CBR/CBT/CB7) is unwritable and repacks to ``<stem>.cbz``.
        """
        if not self._path:
            reason = "Cannot write archive metadata without a path."
            raise ArchiveWriteError(reason)
        is_zip = self._archive_cls == ZipFile
        is_pdf_in_place = self._archive_is_pdf and not self._config.convert.cbz
        if is_zip or is_pdf_in_place:
            return self._path
        destination = self._path.with_suffix(_CBZ_SUFFIX)
        if _same_path(destination, self._path):
            self._refuse_misnamed_archive(self._path)
        return destination

    def _refuse_misnamed_archive(self, path: Path) -> None:
        """
        Refuse to write a RAR, 7z or tar archive already named ``.cbz``.

        Its CBZ would land on the archive itself, and the write called zip
        methods on it and failed with an AttributeError.
        """
        file_type = self._file_type or FileTypeEnum.CBR
        kind = _ARCHIVE_KINDS.get(file_type, file_type.value)
        reason = (
            f"{path} is a {kind} archive named {path.suffix}"
            f" (not a zip): rename it to .{file_type.value.lower()} and comicbox"
            " can convert it to a CBZ."
        )
        raise UnsupportedArchiveTypeError(reason)

    def _get_new_archive_path(self) -> Path:
        """Return the conversion destination, refusing one already on disk."""
        destination = self.get_write_destination()
        if destination != self._path and destination.is_file():
            # self._path is non-None: get_write_destination raised otherwise.
            raise DestinationOccupiedError(
                self._path,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
                destination,
                "convert",
            )
        return destination

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

    def _rewritten_names(self, files: Mapping[str, Any]) -> frozenset[str] | None:
        """
        Name, in lower case, the tag files a write replaces; None for all of them.

        Under ``keep`` a write replaces only the files it writes, so a tag
        file it did not read stays as it is.
        """
        if not self._config.write.keep_formats:
            return None
        return frozenset(Path(name).name.lower() for name in files)

    def _archive_remove_metadata_files(
        self, zf: ZipFile, only: frozenset[str] | None = None
    ) -> None:
        """Remove metadata files from archive: all, or ``only`` those named."""
        for path in self.namelist():
            fn = Path(path).name.lower()
            if fn in ALL_ARCHIVE_METADATA_FILENAMES and (only is None or fn in only):
                # zipremove patches remove()/repack() onto the stdlib
                # ZipFile, which lacks both through at least Python 3.14,
                # so the typeshed stubs can't see either method.
                zf.remove(path)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
        zf.repack()  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]

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
    def _get_filename_from_info(
        info: InfoType, rewritten: frozenset[str] | None = None
    ) -> str | None:
        """
        Get the filename to write.

        Old metadata files are not copied: all of them, or under ``keep``
        only the ``rewritten`` ones, so a tag file not read is copied as is.
        """
        # Do not write dirs.
        # Prevents empty dirs. Files write implicit parents.
        if ArchiveInfo.is_dir(info):
            return None

        filename = ArchiveInfo.filename(info)

        # Don't copy old metadata files to new archive.
        lower_name = Path(filename).name.lower()
        if lower_name in ALL_ARCHIVE_METADATA_FILENAMES and (
            rewritten is None or lower_name in rewritten
        ):
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

    def _copy_archive_files_to_new_archive(
        self, zf: ZipFile, rewritten: frozenset[str] | None = None
    ) -> None:
        # copy all files that are *not* metadata files into new archive.
        if not self._archive_cls or not self._path:
            reason = "Cannot write archive metadata without and archive path."
            raise ArchiveWriteError(reason)
        filenames = tuple(
            filename
            for info in self.infolist()
            if (filename := self._get_filename_from_info(info, rewritten))
        )
        # Default pdf pages to whole-page jpegs: comic readers (and
        # comicbox's own page regex) don't recognize raw pixmap ppm
        # data, and the page render applies pdf display rotation.
        pdf_format = self._get_pdf_format(default=PAGE_FORMAT_PIXMAP_JPEG)
        # Read in batches. Reading a 7z member on its own re-decompresses
        # its whole solid block, so copying page by page made conversion
        # cost grow with the square of the page count.
        for filename in self._iter_prefetched(filenames):
            props = {}
            data = self._archive_readfile(filename, pdf_format=pdf_format, props=props)
            write_name = self._ensure_image_suffix(filename, props)
            # images usually end up slightly larger with zip compression,
            # so store them. Decide from the final name — pdf pages only
            # gain their image suffix above.
            compress = (
                ZIP_DEFLATED
                if self.IMAGE_EXT_RE.search(write_name) is None
                else ZIP_STORED
            )
            zf.writestr(
                write_name,
                data,
                compress_type=compress,
                compresslevel=9,
            )

    def _patch_zipfile(self, files: Mapping[str, bytes], comment: bytes | None) -> None:
        """
        In place remove and append to existing zipfile.

        A ``comment`` of None, from a ``keep`` write, leaves the comment.
        """
        if not self._path:
            reason = "No zipfile path to write to."
            raise ArchiveWriteError(reason)
        rewritten = self._rewritten_names(files)
        self.close()
        with ZipFile(self._path, "a") as zf:
            self._archive_remove_metadata_files(zf, rewritten)
            self._archive_write_metadata_files(zf, files)
            if comment is not None:
                zf.comment = comment

    def _create_zipfile(self, files: Mapping, comment: bytes | None) -> None:
        """
        Create new zipfile.

        A ``comment`` of None, from a ``keep`` write, carries the old
        archive's comment over.
        """
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ArchiveWriteError(reason)
        # Keep the whole source name in the temp file's. Sharing one temp
        # path between archives that differ only by suffix let concurrent
        # writers unlink each other's in-progress file and then replace a
        # half-written one onto the destination.
        tmp_path = self._path.with_name(self._path.name + _RECOMPRESS_SUFFIX)
        new_path = self._get_new_archive_path()
        tmp_path.unlink(missing_ok=True)
        logger.info(f"Creating {new_path}...")
        with ZipFile(tmp_path, "x") as zf:
            # Pages first, metadata last. A later in-place re-tag removes the
            # trailing metadata and appends the new copy, so repack has nothing
            # after it to shift: no page byte is ever rewritten, and a write
            # interrupted partway can only damage bytes past the last page.
            # Metadata written first sat at offset 0 and made every subsequent
            # write slide the whole archive down over its own pages.
            self._copy_archive_files_to_new_archive(zf, self._rewritten_names(files))
            self._archive_write_metadata_files(zf, files)
            zf.comment = self._get_comment() if comment is None else comment

        # Cleanup
        self.close()
        self._cleanup_tmp_archive(tmp_path, new_path)

    def _read_unrewritten_pdf_files(
        self, pf: ZipFile, files: Mapping[str, Any]
    ) -> dict[str, bytes]:
        """
        Under ``keep``, read the PDF's tag files this write does not replace.

        pymupdf's ``embfile_del`` removes the right file only when it is the
        first embedded one; any other takes part of its neighbour with it. So
        a PDF write removes every tag file in order, as one without ``keep``
        always has, and ``keep`` puts these back as they were.
        """
        if (rewritten := self._rewritten_names(files)) is None:
            return {}
        return {
            path: pf.read(path)
            for path in self.namelist()
            if (name := Path(path).name.lower()) in ALL_ARCHIVE_METADATA_FILENAMES
            and name not in rewritten
        }

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
                unread = self._read_unrewritten_pdf_files(pf, files)
                self._archive_remove_metadata_files(pf)
                self._archive_write_metadata_files(pf, {**unread, **files})

    def write_archive_metadata(
        self, files: Mapping, comment: bytes | None, mupdf_metadata: Mapping
    ) -> None:
        """
        Write the metadata files and comment to an archive.

        Pure file I/O: cache invalidation after the rewrite is the dump
        layer's job (ComicboxDump._reset_caches_after_write).

        Every write claims its destination, not just the conversions. An
        in-place rewrite is as destructive as a conversion when two writers
        overlap on it -- ``bulk_write``'s preflight refuses a path named
        twice; the claim is the backstop for concurrent callers -- and the
        finished-file check cannot see a write that is still in flight.
        """
        if not self._path:
            reason = "Cannot write archive metadata without a path."
            raise ArchiveWriteError(reason)
        destination = self.get_write_destination()
        is_zip = self._archive_cls == ZipFile
        _claim_destination(destination, self._path)
        try:
            if is_zip:
                self._patch_zipfile(files, comment)
            elif destination == self._path:
                self._update_pdffile(files, mupdf_metadata)
            else:
                self._create_zipfile(files, comment)
        finally:
            _release_destination(destination)
