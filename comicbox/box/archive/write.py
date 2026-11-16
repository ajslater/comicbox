"""Comicboxs methods for writing to the archive."""

import os
import shutil
import unicodedata
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from threading import Lock
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from loguru import logger
from zipremove import ZIP_DEFLATED, ZIP_STORED, ZipFile

from comicbox._pdf import PAGE_FORMAT_PIXMAP_JPEG
from comicbox.box.archive.archiveinfo import ArchiveInfo, InfoType
from comicbox.box.archive.attributes import keep_attributes
from comicbox.box.archive.journal import TAIL_CAP, TailJournal, replay_journal
from comicbox.box.archive.journal.record import hidden_name
from comicbox.box.archive.read import ComicboxArchiveRead
from comicbox.box.archive.tag_names import ALL_ARCHIVE_METADATA_FILENAMES
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import (
    ArchiveWriteError,
    DestinationOccupiedError,
    UnsafePdfAttachmentError,
    UnsupportedArchiveTypeError,
)

if TYPE_CHECKING:
    from pdffile import PDFFile

FileKey: TypeAlias = tuple[int, int] | tuple[int, int, str] | Path

# A conversion's temporary archive: a dot name ending in .tmp, never a comic
# suffix, so a library watcher skips its creation and its replace alike.
_TMP_ARCHIVE_SUFFIX = ".comicbox.tmp"
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

    Two paths are one file when they resolve to the same real path, which
    sees through a symlink or a linked directory; when they share a device
    and a non-zero inode and the file has more than one link: hard links;
    or when they share a device and a non-zero inode and their real paths
    are equal once case-folded and Unicode-normalized: two spellings of one
    name on a case-insensitive disk, or its NFC and NFD forms on one that
    normalizes names, as macOS does. An inode alone is not trusted, as some network
    and FUSE filesystems give every file the same one. A path with nothing
    there yet, such as a conversion's destination, is its resolved spelling.
    """
    try:
        stat = path.stat()
    except OSError:
        return path.resolve()
    if not stat.st_ino:
        return path.resolve()
    if stat.st_nlink > 1:
        return (stat.st_dev, stat.st_ino)
    real = unicodedata.normalize("NFC", str(path.resolve()).casefold())
    return (stat.st_dev, stat.st_ino, real)


def tmp_archive_path(path: Path) -> Path:
    """Name the temporary archive a conversion of this one writes first."""
    return path.with_name(hidden_name(path.name, _TMP_ARCHIVE_SUFFIX))


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

    @staticmethod
    def _is_replaced(name: str, rewritten: frozenset[str] | None) -> bool:
        """Tell whether a write replaces this member: a tag file, rewritten."""
        lower_name = Path(name).name.lower()
        return lower_name in ALL_ARCHIVE_METADATA_FILENAMES and (
            rewritten is None or lower_name in rewritten
        )

    def _archive_remove_metadata_files(
        self, zf: ZipFile, only: frozenset[str] | None = None
    ) -> None:
        """Remove metadata files from archive: all, or ``only`` those named."""
        # zipremove patches remove()/repack() onto the stdlib ZipFile, which
        # lacks both through at least Python 3.14, so the typeshed stubs
        # can't see either method.
        removed = [
            zf.remove(info)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
            for info in tuple(zf.infolist())
            if self._is_replaced(info.filename, only)
        ]
        # Strip only these. A bare repack() strips every unreferenced entry
        # it finds, before the tail as well, which no rollback could see.
        zf.repack(removed)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]

    def _archive_write_metadata_files(
        self, zf: "ZipFile | PDFFile", files: Mapping[str, bytes]
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

    @classmethod
    def _get_filename_from_info(
        cls, info: InfoType, rewritten: frozenset[str] | None = None
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
        if cls._is_replaced(filename, rewritten):
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
        written: set[str] = set()
        for filename in self._iter_prefetched(filenames):
            props = {}
            data = self._archive_readfile(filename, pdf_format=pdf_format, props=props)
            write_name = self._ensure_image_suffix(filename, props)
            self._refuse_a_page_named_twice(write_name, written)
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

    def _refuse_a_page_named_twice(self, write_name: str, written: set[str]) -> None:
        """
        Refuse a PDF whose attachment takes the name a page converts to.

        Page 1 converts to ``1.jpeg``, so an attachment named ``1.jpeg`` and
        the page were both written under one name and one was lost. Which
        name a page takes depends on its format, and for the image formats on
        the page, so it is caught as it is written; the temporary archive is
        then discarded, and the comic is as it was.
        """
        if self._archive_is_pdf and write_name in written:
            reason = (
                f"{self._path}: cannot convert it to a CBZ without harming the"
                f" attachment {write_name!r}, which is also the name of a page it"
                " converts."
            )
            raise UnsafePdfAttachmentError(reason)
        written.add(write_name)

    def _tail_offset(self, path: Path, rewritten: frozenset[str] | None) -> int | None:
        """
        Find the first byte an in-place write changes; None to copy the archive.

        It is the lower of the first removed tag file's offset and the start
        of the central directory: the write changes every byte from there to
        the end, and none before. A tag file stored before a member that is
        kept, as when another tool wrote ComicInfo.xml first, would have every
        later member slid down over its old place; that write, and one whose
        tail is over ``TAIL_CAP``, copies the archive instead. The copy puts
        pages first and tags last, so every later write patches the tail.
        """
        with ZipFile(path) as zf:
            infos = zf.infolist()
            start_dir = zf.start_dir
        removed = [
            info.header_offset
            for info in infos
            if self._is_replaced(info.filename, rewritten)
        ]
        offset = min((*removed, start_dir))
        kept_after = any(
            info.header_offset > offset
            for info in infos
            if not self._is_replaced(info.filename, rewritten)
        )
        if kept_after or path.stat().st_size - offset > TAIL_CAP:
            return None
        return offset

    def _patch_zipfile(self, files: Mapping[str, bytes], comment: bytes | None) -> None:
        """
        In place remove and append to existing zipfile.

        Only the tail changes, and ``TailJournal`` puts it back if the write
        fails, or, through its journal, if it is killed part way.
        A ``comment`` of None, from a ``keep`` write, leaves the comment.
        """
        if not self._path:
            reason = "No zipfile path to write to."
            raise ArchiveWriteError(reason)
        rewritten = self._rewritten_names(files)
        self.close()
        # A killed copy's leftover temporary archive goes with the next write.
        with suppress(OSError):
            tmp_archive_path(self._path.resolve()).unlink(missing_ok=True)
        if (offset := self._tail_offset(self._path, rewritten)) is None:
            self._patch_a_copy(self._path, files, comment, rewritten)
            return
        with TailJournal(self._path, offset):
            self._patch_in_place(self._path, files, comment, rewritten)

    def _patch_in_place(
        self,
        path: Path,
        files: Mapping[str, bytes],
        comment: bytes | None,
        rewritten: frozenset[str] | None,
    ) -> None:
        """Remove the tag files a write replaces, repack, and append the new ones."""
        with ZipFile(path, "a") as zf:
            self._archive_remove_metadata_files(zf, rewritten)
            self._archive_write_metadata_files(zf, files)
            if comment is not None:
                zf.comment = comment

    def _patch_a_copy(
        self,
        path: Path,
        files: Mapping[str, bytes],
        comment: bytes | None,
        rewritten: frozenset[str] | None,
    ) -> None:
        """
        Make the in-place write on a copy, then replace the comic with it.

        For a zip whose tail cannot be patched in place: a tag file stored
        before a kept member, or a tail over the cap. The copy is of the real
        file, through any link, and the result is the in-place write's, member
        for member: names, bytes, order, dates, modes and comments are as they
        were, and no page is read. The copy is flushed and given the
        original's extended attributes, owner and group where they may be
        set, and mode before it replaces the real file; a failure anywhere
        leaves the original and no temporary file. A directory that cannot
        take the copy, read-only or full, gets the in-place write unprotected,
        with a warning, as before the copy path.
        """
        real = path.resolve()
        if replay_journal(real):
            reason = f"{real} was restored from an interrupted write: write it again."
            raise ArchiveWriteError(reason)
        logger.debug(f"{real}: writing a copy, pages first, tags last.")
        tmp_path = tmp_archive_path(real)
        try:
            shutil.copyfile(real, tmp_path)
        except OSError as exc:
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            logger.warning(
                f"{real}: no room for a copy beside it ({exc}); writing it in"
                " place, unprotected: a write that fails part way can damage it."
            )
            self._patch_in_place(real, files, comment, rewritten)
            return
        try:
            self._patch_in_place(tmp_path, files, comment, rewritten)
            with tmp_path.open("r+b") as copy:
                os.fsync(copy.fileno())
            keep_attributes(real, tmp_path)
            tmp_path.replace(real)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def _create_zipfile(self, files: Mapping, comment: bytes | None) -> None:
        """
        Convert to a new zipfile: a CBR, CBT, CB7 or PDF repacked as a CBZ.

        A ``comment`` of None, from a ``keep`` write, carries the old
        archive's comment over.
        """
        if not self._path:
            reason = "Cannot write zipfile metadata without a path."
            raise ArchiveWriteError(reason)
        if self._archive_is_pdf:
            self._refuse_unconvertible_pdf(files)
        # Keep the whole source name in the temp file's. Sharing one temp
        # path between archives that differ only by suffix let concurrent
        # writers unlink each other's in-progress file and then replace a
        # half-written one onto the destination. A leftover from a write
        # that was killed is removed here.
        tmp_path = tmp_archive_path(self._path)
        new_path = self._get_new_archive_path()
        tmp_path.unlink(missing_ok=True)
        logger.info(f"Creating {new_path}...")
        try:
            with ZipFile(tmp_path, "x") as zf:
                # Pages first, metadata last. A later in-place re-tag removes
                # the trailing metadata and appends the new copy, so repack has
                # nothing after it to shift: no page byte is ever rewritten.
                # Metadata written first sat at offset 0 and made every
                # subsequent write slide the whole archive down over its pages.
                self._copy_archive_files_to_new_archive(
                    zf, self._rewritten_names(files)
                )
                self._archive_write_metadata_files(zf, files)
                zf.comment = self._get_comment() if comment is None else comment
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        # Cleanup
        self.close()
        self._cleanup_tmp_archive(tmp_path, new_path)

    @staticmethod
    def _names_a_page(pf: "PDFFile", name: str) -> bool:
        """Tell whether pdffile reads this name as a page, not an attachment."""
        try:
            pf.valid_pagenum(name)
        except ValueError:
            return False
        return True

    def _refuse_unsafe_pdf_attachments(
        self,
        pf: "PDFFile",
        embedded: list[str],
        kept: list[str],
        doing: str = "replace its tag files",
    ) -> None:
        """
        Refuse an attachment that cannot be put back as it was.

        pdffile reads and removes a name that is a page number as that page,
        and pymupdf finds an embedded file by its first name only, so either
        would delete a page or lose an attachment.
        """
        for name in kept:
            if self._names_a_page(pf, name):
                why = "is also the name of a page"
            elif embedded.count(name) > 1:
                why = "is the name of more than one attachment"
            else:
                continue
            reason = (
                f"{self._path}: cannot {doing} without harming the"
                f" attachment {name!r}, which {why}."
            )
            raise UnsafePdfAttachmentError(reason)

    @staticmethod
    def _pdf_embedded_names(pf: "PDFFile") -> list[str]:
        """List a PDF's embedded files, in its own order."""
        names = pf.namelist()
        # pdffile lists the embedded files in the PDF's own order, then pages.
        return names[: len(names) - len(pf.pagelist())]

    def _refuse_unconvertible_pdf(self, files: Mapping[str, Any]) -> None:
        """
        Refuse a PDF whose attachments a conversion would not carry over whole.

        One named like a page number was read as that page, so the CBZ had
        the page twice and lost the attachment; one of two sharing a name
        was lost the same way.
        """
        pf = cast("PDFFile", self._get_archive())
        embedded = self._pdf_embedded_names(pf)
        rewritten = self._rewritten_names(files)
        kept = [name for name in embedded if not self._is_replaced(name, rewritten)]
        self._refuse_unsafe_pdf_attachments(pf, embedded, kept, "convert it to a CBZ")

    def _replace_pdf_tag_files(self, pf: "PDFFile", files: Mapping[str, bytes]) -> None:
        """
        Replace a PDF's tag files, leaving every other attachment's bytes as they were.

        pymupdf's ``embfile_del`` removes an embedded file rightly only when
        it is the first: for any other it removes that file's name and the
        previous file's contents, leaving the previous name holding this
        file's bytes. So attachments are only ever removed from the front.
        Every attachment up to the last one this write replaces is read and
        removed first to last, and those it does not replace (other
        attachments, and under ``keep`` the tag files it did not read) are
        added back in their old order, before the new tag files. The
        attachments after the last replaced one are not touched.
        """
        rewritten = self._rewritten_names(files)
        embedded = self._pdf_embedded_names(pf)
        replaced = [self._is_replaced(name, rewritten) for name in embedded]
        last = max(
            (i for i, is_replaced in enumerate(replaced) if is_replaced), default=-1
        )
        front = embedded[: last + 1]
        kept = [
            name
            for name, is_replaced in zip(front, replaced, strict=False)
            if not is_replaced
        ]
        self._refuse_unsafe_pdf_attachments(pf, embedded, kept)
        kept_files = {name: pf.read(name) for name in kept}
        for name in front:
            pf.remove(name)
        self._archive_write_metadata_files(pf, {**kept_files, **files})

    def _update_pdffile(self, files: Mapping, mupdf_metadata: Mapping) -> None:
        if not self._path:
            reason = "No pdfile path to write to."
            raise ArchiveWriteError(reason)
        if not self._archive_cls:
            reason = "PDF archive class not initialized."
            raise ArchiveWriteError(reason)
        self.close()
        delete_all_tags = self._config.write.delete_all_tags
        pf = self._archive_cls(self._path)
        try:
            if delete_all_tags or mupdf_metadata:
                pf.write_metadata(mupdf_metadata)
            # As in a zip, a write without keep replaces every tag file, so
            # -w pdf alone removes them and what it wrote is what reads back.
            # Under keep only those rewritten are; with none it does nothing.
            self._replace_pdf_tag_files(pf, files)
        except BaseException:
            # pdffile's close() saves a changed document even after an
            # error, which wrote a half-done write over the PDF. Dropped
            # unsaved, the PDF on disk is as it was.
            del pf
            raise
        # pdffile saves to a temporary file and replaces the PDF with it.
        pf.close()

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
