"""Special file writes."""

from collections.abc import Mapping
from pathlib import Path

from loguru import logger

from comicbox.box.archive import archive_close
from comicbox.box.dump import ComicboxDump
from comicbox.formats import MetadataFormats


class ComicboxDumpToFiles(ComicboxDump):
    """Special file writes."""

    @archive_close
    def to_file(
        self,
        dest_path=None,
        metadata: Mapping | None = None,
        fmt: MetadataFormats = MetadataFormats.COMICBOX_JSON,
        embed_fmt: MetadataFormats | None = None,
        **kwargs,
    ):
        """Export metadatat to a file with a schema."""
        if dest_path is None:
            dest_path = self._config.dest_path
        dest_path = Path(dest_path)
        if metadata is None:
            metadata = self._get_metadata()
        fn = fmt.value.filename
        path = dest_path / fn
        try:
            schema, denormalized_metadata = self._to_dict(fmt, embed_fmt)
            schema.dumpf(denormalized_metadata, path, **kwargs)
            logger.info(f"Exported {path}")
        except Exception:
            logger.exception(f"Could not export {fn}")

    @archive_close
    def export_files(self, formats=None, embed_fmt=None):
        """Export metadata to all supported file formats."""
        if self._config.dry_run:
            logger.info("Not exporting files.")
            return
        if not formats:
            formats = self._config.export

        for fmt in formats:
            self.to_file(fmt=fmt, embed_fmt=embed_fmt)

    @archive_close
    def rename_file(self):
        """Rename the archive."""
        if not self._path:
            reason = "Cannot rename archive without a path."
            raise ValueError(reason)
        schema, filename_md = self._to_dict(MetadataFormats.FILENAME)
        fn = schema.dumps(filename_md)
        old_path = self._path
        if not fn:
            logger.warning(f"Unable to construct a filename for {old_path}")
            return
        new_path = self._path.parent / Path(fn)
        if self._config.dry_run:
            logger.info(f"Would rename:\n{old_path} ==> {new_path}")
            return
        self._path.rename(new_path)
        self._path: Path | None = new_path
        logger.info(f"Renamed:\n{old_path} ==> {new_path}")
