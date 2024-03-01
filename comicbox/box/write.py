"""Writing Methods."""

from collections.abc import Mapping
from logging import getLogger
from pathlib import Path

from comicbox.box.archive_read import archive_close
from comicbox.box.archive_write import ComicboxArchiveWriteMixin
from comicbox.box.pages import ComicboxPagesMixin
from comicbox.sources import MetadataSources, SourceFrom
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.pdf import MuPDFTransform

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
        elif self._config.delete:
            sources = ()
        else:
            reason = "No formats specified to write"
            LOG.warning(reason)
            return None
        return sources

    def _get_schema_and_transformed_metadata(
        self, transform_class: type[BaseTransform], metadata: Mapping, sources=()
    ):
        schema = transform_class.SCHEMA_CLASS(path=self._path)
        transform = transform_class(path=self._path)
        write_transforms = (source.value.transform_class for source in sources)
        denormalized_metadata = transform.from_comicbox(
            metadata, write_transforms=write_transforms
        )
        return schema, denormalized_metadata

    def _write_pdf(self, metadata, sources):
        """Write PDF Metadata."""
        if MetadataSources.PDF in self._config.write:
            schema, denormalized_metadata = self._get_schema_and_transformed_metadata(
                MuPDFTransform, metadata, sources
            )
            mupdf_md = schema.dump(denormalized_metadata) or {}
            if not isinstance(mupdf_md, Mapping):
                return None
            pdf_md = mupdf_md.get(schema.ROOT_TAGS[0], {})
            return self.write_pdf_metadata(pdf_md)
        reason = "Can only write pdf format to pdf files."
        LOG.warning(reason)
        return None

    def _write_archive_metadata(self, sources, metadata: Mapping):
        """Prepare archive files and comment and write to archive."""
        # Get files and comment.
        files = {}
        for source in sources:
            if source.value.from_archive == SourceFrom.ARCHIVE_FILE:
                transform_class = source.value.transform_class
                (
                    schema,
                    denormalized_metadata,
                ) = self._get_schema_and_transformed_metadata(transform_class, metadata)
                if denormalized_metadata:
                    files[schema.FILENAME] = schema.dumps(denormalized_metadata)

        if MetadataSources.CBI in sources:
            schema, denormalized_metadata = self._get_schema_and_transformed_metadata(
                ComicBookInfoTransform, metadata
            )
            comment = schema.dumps(denormalized_metadata)
            comment = comment.encode(errors="replace")
        else:
            comment = b""

        # write to the archive.
        return self.write_archive_metadata(files, comment)

    @archive_close
    def write(self, sources=None):
        """Write metadata accourding to config.write settings."""
        if self._config.dry_run or not (
            self._config.write or self._config.cbz or self._config.delete
        ):
            LOG.info(f"Not writing metadata for: {self._path}")
            return None

        # Must get metadata *before* get write sources.
        # metadata = self.get_metadata()
        metadata = self.get_metadata()
        if sources is None:
            sources = self._get_write_sources()
            if sources is None:
                return None

        if self._archive_is_pdf:
            result = self._write_pdf(metadata, sources)
        else:
            result = self._write_archive_metadata(sources, metadata)
        LOG.info(f"Wrote metadata to: {self._path}")
        return result

    ##################
    # SPECIAL WRITES #
    ##################

    @archive_close
    def to_file(
        self,
        dest_path=None,
        metadata: Mapping | None = None,
        transform_class: type[BaseTransform] = ComicboxJsonTransform,
        **kwargs,
    ):
        """Export metadatat to a file with a schema."""
        if dest_path is None:
            dest_path = self._config.dest_path
        dest_path = Path(dest_path)
        if metadata is None:
            metadata = self._get_metadata()
        fn = transform_class.SCHEMA_CLASS.FILENAME
        path = dest_path / fn
        try:
            schema, denormalized_metadata = self._get_schema_and_transformed_metadata(
                transform_class, metadata
            )
            schema.dumpf(denormalized_metadata, path, **kwargs)
            LOG.info(f"Exported {path}")
        except Exception:
            LOG.exception(f"Could not export {fn}")

    @archive_close
    def export_files(self, sources=None):
        """Export metadata to all supported file formats."""
        if self._config.dry_run:
            LOG.info("Not exporting files.")
            return
        if not sources:
            sources = self._config.export

        Path(self._config.dest_path)
        self._get_metadata()
        for source in sources:
            self.to_file(transform_class=source.value.transform_class)

    @archive_close
    def rename_file(self):
        """Rename the archive."""
        if not self._path:
            reason = "Cannot rename archive without a path."
            raise ValueError(reason)
        metadata = self._get_metadata()
        schema, filename_md = self._get_schema_and_transformed_metadata(
            FilenameTransform, metadata
        )
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
