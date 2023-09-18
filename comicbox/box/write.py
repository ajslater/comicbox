"""Writing Methods."""
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path
from typing import Optional

from comicbox.box.archive_read import archive_close
from comicbox.box.archive_write import ComicboxArchiveWriteMixin
from comicbox.box.pages import ComicboxPagesMixin
from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox_base import ComicboxBaseSchema, SchemaConfig
from comicbox.schemas.filename import FilenameSchema
from comicbox.schemas.json import ComicboxJsonSchema
from comicbox.schemas.pdf import PDFSchema
from comicbox.sources import MetadataSources, SourceFrom
from pdffile.pdffile import PDFFile

LOG = getLogger(__name__)


class ComicboxWriteMixin(ComicboxPagesMixin, ComicboxArchiveWriteMixin):
    """Writing Methods."""

    #############################
    # WRITE METADATA TO ARCHIVE #
    #############################

    def _get_write_sources(self):
        loaded_sources = frozenset(self._loaded.keys())
        if self._config.write:
            sources = self._config.write
        elif self._config.cbz:
            sources = loaded_sources
        elif self._config.delete_tags:
            sources = ()
        else:
            reason = "No formats specified to write"
            LOG.warning(reason)
            return None
        return sources

    def _write_pdf(self, metadata, dump_config):
        """Write PDF Metadata."""
        if MetadataSources.PDF in self._config.write:
            schema = PDFSchema(path=self._path, dump_config=dump_config)
            mupdf_md: dict = schema.dump(metadata) or {}
            pdf_md = mupdf_md.get(PDFSchema.MU_ROOT_TAG, {})
            return self.write_pdf_metadata(pdf_md)
        reason = "Can only write pdf format to pdf files."
        LOG.warning(reason)
        return None

    def _write_archive_metadata(self, sources, metadata: Mapping, dump_config):
        """Prepare archive files and comment and write to archive."""
        # Get files and comment.
        files = {}
        for source in sources:
            if source.value.from_archive == SourceFrom.ARCHIVE_FILE:
                schema = source.value.schema_class(self._path, dump_config=dump_config)
                files[schema.FILENAME] = schema.dumps(metadata)

        if MetadataSources.CBI in self._config.write:
            schema = ComicBookInfoSchema(path=self._path, dump_config=dump_config)
            comment = schema.dumps(metadata)
            comment = comment.encode(errors="replace")
        else:
            comment = b""

        # write to the archive.
        self.write_archive_metadata(files, comment)

    @archive_close
    def write(self, sources=None, dump_config: Optional[SchemaConfig] = None):
        """Write metadata accourding to config.write settings."""
        if self._config.dry_run or not (
            self._config.write or self._config.cbz or self._config.delete_tags
        ):
            LOG.info(f"Not writing metadata for: {self._path}")
            return None

        # Must get metadata *before* get write sources.
        metadata = {} if self._config.delete_tags else self.get_metadata()
        if sources is None:
            sources = self._get_write_sources()
            if sources is None:
                return None

        if not dump_config:
            dump_config = self._default_dump_config

        if self._archive_cls == PDFFile:
            result = self._write_pdf(metadata, dump_config)
        else:
            result = self._write_archive_metadata(sources, metadata, dump_config)
        LOG.info(f"Wrote metadata to: {self._path}")
        return result

    ##################
    # SPECIAL WRITES #
    ##################

    @archive_close
    def to_file(
        self,
        dest_path=None,
        metadata: Optional[Mapping] = None,
        schema_class: type[ComicboxBaseSchema] = ComicboxJsonSchema,
        dump_config: Optional[SchemaConfig] = None,
        **kwargs,
    ):
        """Export metadatat to a file with a schema."""
        if dest_path is None:
            dest_path = self._config.dest_path
        dest_path = Path(dest_path)
        if metadata is None:
            metadata = self._get_metadata()
        fn = schema_class.FILENAME
        path = dest_path / fn
        try:
            if not dump_config:
                dump_config = self._default_dump_config
            schema = schema_class(self._path, dump_config=dump_config)
            schema.dumpf(metadata, path, **kwargs)
            LOG.info(f"Exported {path}")
        except Exception as exc:
            LOG.warn(f"Could not export {fn}: {exc}")

    @archive_close
    def export_files(self, sources=None, dump_config: Optional[SchemaConfig] = None):
        """Export metadata to all supported file formats."""
        if self._config.dry_run:
            LOG.info("Not exporting files.")
            return
        if not sources:
            sources = self._config.export

        Path(self._config.dest_path)
        self._get_metadata()
        if not dump_config:
            dump_config = self._default_dump_config
        for source in sources:
            self.to_file(
                schema_class=source.value.schema_class, dump_config=dump_config
            )

    @archive_close
    def rename_file(self, dump_config: Optional[SchemaConfig] = None):
        """Rename the archive."""
        if not self._path:
            reason = "Cannot rename archive without a path."
            raise ValueError(reason)
        metadata = self._get_metadata()
        if not dump_config:
            dump_config = self._default_dump_config
        schema = FilenameSchema(path=self._path, dump_config=dump_config)
        filename_md = schema.load(metadata)
        fn = schema.dumps(filename_md)
        old_path = self._path
        if not fn:
            LOG.warning(f"Unable to construct a filename for {old_path}")
            return
        new_path = self._path.parent / Path(fn)
        if self._config.dry_run:
            LOG.info(f"Would rename:\n{old_path} ==> {new_path}")
            return
        self._path.rename(new_path)
        self._path = new_path
        LOG.info(f"Renamed:\n{old_path} ==> {new_path}")
