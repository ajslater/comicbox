"""Writing Methods."""

from collections.abc import Mapping

from loguru import logger

from comicbox.box.archive.init import archive_close
from comicbox.box.pages import ComicboxPages
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources

ARCHIVE_FORMATS = frozenset(
    MetadataSources.ARCHIVE_FILE.value.formats
    + MetadataSources.ARCHIVE_COMMENT.value.formats
)


class ComicboxDump(ComicboxPages):
    """Writing Methods."""

    def _get_dump_formats(self):
        formats = ()
        if self._config.write:
            formats = self._config.write
        elif self._config.cbz:
            loaded_data_lists = (
                self.get_loaded_metadata(source) for source in MetadataSources
            )
            formats = frozenset(
                loaded_data.fmt
                for loaded_data_list in loaded_data_lists
                if loaded_data_list
                for loaded_data in loaded_data_list
                if loaded_data
            )
        elif self._config.delete_all_tags:
            reason = "Deleting all tags."
            logger.warning(reason)
        else:
            reason = "No formats specified to write"
            logger.warning(reason)
            formats = None
        return formats

    def _dump_to_pdf(self, formats):
        """Write PDF Metadata."""
        if MetadataFormats.PDF not in self._config.write:
            reason = "Can only write pdf format to pdf files."
            logger.warning(reason)
            return None

        for embed_fmt in MetadataSources.EMBEDDED.value.formats:
            if embed_fmt in formats:
                break
        else:
            embed_fmt = None

        schema, denormalized_metadata = self._to_dict(MetadataFormats.PDF, embed_fmt)
        mupdf_md = schema.dump(denormalized_metadata) or {}
        if not isinstance(mupdf_md, Mapping):
            return None
        pdf_md = mupdf_md.get(schema.ROOT_TAG, {})
        return self.write_pdf_metadata(pdf_md)

    def _dump_to_archive(self, formats):
        """Prepare archive files and comment and write to archive."""
        # Get files and comment.
        files = {}
        comment = b""
        for fmt in formats:
            if fmt not in ARCHIVE_FORMATS:
                continue
            (
                schema,
                denormalized_metadata,
            ) = self._to_dict(fmt)
            if not denormalized_metadata:
                continue
            if fmt in MetadataSources.ARCHIVE_FILE.value.formats:
                files[fmt.value.filename] = schema.dumps(denormalized_metadata)
            elif fmt in MetadataSources.ARCHIVE_COMMENT:
                comment = schema.dumps(denormalized_metadata)
                comment = comment.encode(errors="replace")

        # write to the archive.
        return self.write_archive_metadata(files, comment)

    @archive_close
    def dump(self, formats=None):
        """Write metadata according to config.write settings."""
        if self._config.dry_run or not (
            self._config.write or self._config.cbz or self._config.delete_all_tags
        ):
            logger.info(f"Not writing metadata for: {self._path}")
            return None

        # Must get metadata *before* get write formats
        if formats is None:
            formats = self._get_dump_formats()
            if formats is None:
                return None

        if self._archive_is_pdf:
            result = self._dump_to_pdf(formats)
        else:
            result = self._dump_to_archive(formats)
        logger.info(f"Wrote metadata to: {self._path}")
        return result
