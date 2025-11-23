"""Writing Methods."""

from collections.abc import Mapping

from loguru import logger

from comicbox.box.pages import ComicboxPages
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources

ARCHIVE_FORMATS = frozenset(
    MetadataSources.ARCHIVE_FILE.value.formats
    + MetadataSources.ARCHIVE_COMMENT.value.formats
)


class ComicboxDump(ComicboxPages):
    """Writing Methods."""

    def _get_dump_formats(self) -> frozenset[MetadataFormats] | None:
        formats = frozenset()
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
        elif not self._config.delete_all_tags:
            reason = "No formats specified to write"
            logger.warning(reason)
            formats = None
        else:
            reason = "Deleting all tags."
            logger.warning(reason)

        return formats

    def _dump_format_to_archive(
        self,
        fmt: MetadataFormats,
        files: dict[str, Mapping],
        pdf_md: dict,
        comment: dict[str, bytes],
    ):
        if fmt not in ARCHIVE_FORMATS:
            return
        (
            schema,
            denormalized_metadata,
        ) = self._to_dict(fmt)
        if not denormalized_metadata:
            return
        if fmt == MetadataFormats.PDF:
            schema, denormalized_metadata = self._to_dict(MetadataFormats.PDF)
            mupdf_md = schema.dump(denormalized_metadata) or {}
            if isinstance(mupdf_md, Mapping):
                pdf_md.update(mupdf_md.get(schema.ROOT_TAG, {}))
        elif fmt in MetadataSources.ARCHIVE_FILE.value.formats:
            files[fmt.value.filename] = schema.dumps(denormalized_metadata)
        elif fmt in MetadataSources.ARCHIVE_COMMENT.value.formats:
            cmnt = schema.dumps(denormalized_metadata)
            cmnt = cmnt.encode(errors="replace")
            comment["c"] = cmnt

    def _dump_to_archive(self, formats: frozenset[MetadataFormats]):
        """Prepare archive files and comment and write to archive."""
        # Get files and comment.
        files = {}
        comment = {"c": b""}
        pdf_md = {}
        if not self._config.delete_all_tags:
            for fmt in formats:
                self._dump_format_to_archive(fmt, files, pdf_md, comment)

        # write to the archive.
        return self.write_archive_metadata(files, comment["c"], pdf_md)

    def dump(self, formats: frozenset[MetadataFormats] | None = None):
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

        result = None
        if self._config.cbz or self._config.delete_all_tags or formats:
            result = self._dump_to_archive(formats)
        logger.info(f"Wrote metadata to: {self._path}")
        return result
