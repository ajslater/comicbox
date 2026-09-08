"""Special file writes."""

from pathlib import Path
from typing import Any

from loguru import logger

from comicbox.box.archive.write import _claim_destination, _release_destination
from comicbox.box.dump import ComicboxDump
from comicbox.exceptions import ArchiveWriteError, ExportError
from comicbox.formats import MetadataFormats


class ComicboxDumpToFiles(ComicboxDump):
    """Special file writes."""

    def to_file(
        self,
        dest_path: Path | str | None = None,
        fmt: MetadataFormats = MetadataFormats.COMICBOX_JSON,
        **kwargs: Any,
    ) -> None:
        """Export metadatat to a file with a schema."""
        if dest_path is None:
            dest_path = self._config.general.dest_path
        dest_path = Path(dest_path)
        fn = fmt.value.filename
        path = dest_path / fn
        if not path.resolve().is_relative_to(dest_path.resolve()):
            reason = f"Unsafe path escapes destination: {path}"
            raise ExportError(reason)
        try:
            schema, denormalized_metadata = self._to_dict(fmt)
            schema.dumpf(denormalized_metadata, path, **kwargs)
            logger.info(f"Exported {path}")
        except Exception:
            logger.exception(f"Could not export {fn}")

    def export_files(self, formats: frozenset[MetadataFormats] | None = None) -> None:
        """Export metadata to all supported file formats."""
        if self._config.general.dry_run:
            logger.info("Not exporting files.")
            return
        if not formats:
            formats = self._config.convert.export_formats
        if not formats:
            return

        for fmt in formats:
            self.to_file(fmt=fmt)

    def predict_filename(self) -> str:
        """
        Return the scheme filename this archive would be renamed to.

        The rendered name ends in ``ext``, which is a *metadata* field
        rather than the file's suffix. Left to the merge it can be missing
        (a config that skips or deletes it, whereupon comicfn2dict falls
        back to its "cbz" default) or stale (a value some tagger embedded
        in the archive), either of which names a PDF as a zip. The archive
        on disk is the authority, so its own suffix always wins.

        Returns "" when no usable name could be built, including a name
        that is nothing but an extension — renaming to that would make a
        hidden file.
        """
        schema, filename_md = self._to_dict(MetadataFormats.FILENAME)
        fn = schema.dumps(filename_md)
        if not fn or fn.startswith("."):
            return ""
        if self._path:
            fn = str(Path(fn).with_suffix(self._path.suffix))
        return fn

    @staticmethod
    def _is_same_file(old_path: Path, new_path: Path) -> bool:
        """Return whether both names already refer to one file on disk."""
        # Not just `==`: on a case-insensitive filesystem a rename that only
        # changes case lands on the same inode, and refusing it would make
        # `--rename` fail on every macOS library.
        try:
            return new_path.samefile(old_path)
        except OSError:
            return False

    def _rename_to(self, old_path: Path, new_path: Path) -> None:
        """
        Rename onto a destination no one else holds.

        Path.rename() replaces an existing destination silently on posix,
        so two archives whose metadata predicts one name -- the same issue
        carried twice, or a scheme that renders too few fields -- left only
        the last one written. Claim the destination for the same reason
        conversions do (comicbox.box.archive.write): the finished-file
        check alone can't see a rename still in flight on another thread.
        """
        if self._is_same_file(old_path, new_path):
            return
        _claim_destination(new_path)
        try:
            if new_path.exists():
                reason = f"{new_path} already exists."
                raise ArchiveWriteError(reason)
            old_path.rename(new_path)
        finally:
            _release_destination(new_path)

    def rename_file(self) -> None:
        """Rename the archive."""
        if not self._path:
            reason = "Cannot rename archive without a path."
            raise ArchiveWriteError(reason)
        fn = self.predict_filename()
        old_path = self._path
        if not fn:
            logger.warning(f"Unable to construct a filename for {old_path}")
            return
        new_path = self._path.parent / Path(fn)
        if self._config.general.dry_run:
            logger.info(f"Would rename:\n{old_path} ==> {new_path}")
            return
        self._rename_to(old_path, new_path)
        self._path: Path | None = new_path
        logger.info(f"Renamed:\n{old_path} ==> {new_path}")
