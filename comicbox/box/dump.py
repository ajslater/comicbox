"""Writing Methods."""

from collections.abc import Mapping

from loguru import logger

from comicbox.box.pages import ComicboxPages
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources

ARCHIVE_FORMATS = frozenset(
    MetadataSources.ARCHIVE_FILE.value.formats
    + MetadataSources.ARCHIVE_COMMENT.value.formats
)


class ComicboxDump(ComicboxPages):
    """Writing Methods."""

    def _get_dump_formats(self) -> frozenset[MetadataFormats] | None:
        write = self._config.write
        convert = self._config.convert
        formats: frozenset[MetadataFormats] | None = frozenset()
        if write.formats:
            formats = write.formats
        elif convert.cbz:
            loaded_data_lists = (
                self.get_loaded_metadata(source) for source in MetadataSources
            )
            formats = frozenset(
                loaded_data.fmt
                for loaded_data_list in loaded_data_lists
                if loaded_data_list
                for loaded_data in loaded_data_list
                if loaded_data and loaded_data.fmt is not None
            )
        elif not write.delete_all_tags:
            reason = "No formats specified to write"
            logger.warning(reason)
            formats = None
        else:
            reason = "Deleting all tags."
            logger.warning(reason)

        return formats

    def _ensure_pdf_to_cbz_default_format(
        self, formats: frozenset[MetadataFormats]
    ) -> frozenset[MetadataFormats]:
        """If no formats given to PDF -> CBZ convert default to ComicInfo."""
        if self._config.convert.cbz:
            formats_without_pdf = formats - {MetadataFormats.PDF}
            if not formats_without_pdf:
                logger.info(
                    "PDF→CBZ conversion with no --write formats; "
                    "defaulting to ComicInfo."
                )
                formats = frozenset(formats_without_pdf | {MetadataFormats.COMIC_INFO})
        return formats

    def _dump_format_to_archive(
        self,
        fmt: MetadataFormats,
        files: dict[str, Mapping],
        pdf_md: dict,
        comment: dict[str, bytes],
    ) -> None:
        if fmt not in ARCHIVE_FORMATS:
            return

        (
            schema,
            denormalized_metadata,
        ) = self._to_dict(fmt)
        if not denormalized_metadata:
            return
        if fmt == MetadataFormats.PDF and not self._config.convert.cbz:
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

    def _dump_to_archive(self, formats: frozenset[MetadataFormats]) -> None:
        """Prepare archive files and comment and write to archive."""
        # Get files and comment.
        files = {}
        comment = {"c": b""}
        pdf_md = {}
        if not self._config.write.delete_all_tags:
            formats = self._ensure_pdf_to_cbz_default_format(formats)
            for fmt in formats:
                self._dump_format_to_archive(fmt, files, pdf_md, comment)

        # write to the archive, then re-seed caches from the new bytes.
        self.write_archive_metadata(files, comment["c"], pdf_md)
        self._reset_caches_after_write()

    def _reset_caches_after_write(self) -> None:
        """
        Re-seed the box caches from the now-rewritten archive.

        Everything parsed from the old archive bytes is stale after a
        write; only the caller-injected API source survives (it didn't
        come from the file). Lives here rather than in the archive write
        layer so file I/O stays decoupled from the source-cache
        lifecycle.
        """
        old_api_source_data_list = self._sources.get(MetadataSources.API)
        if old_api_source_data_list:
            old_api_source_data = old_api_source_data_list[0]
            old_api_source_metadata = old_api_source_data.data
            old_api_source_format = old_api_source_data.fmt
        else:
            old_api_source_metadata = None
            old_api_source_format = None
        self._reset_archive(old_api_source_format, old_api_source_metadata)

    def dump(self, formats: frozenset[MetadataFormats] | None = None) -> None:
        """Write metadata according to config.write settings."""
        write = self._config.write
        convert = self._config.convert
        if self._config.general.dry_run or not (
            write.formats or convert.cbz or write.delete_all_tags
        ):
            logger.info(f"Not writing metadata for: {self._path}")
            return None

        # Must get metadata *before* get write formats
        if formats is None:
            formats = self._get_dump_formats()
            if formats is None:
                return None

        result = None
        if formats or convert.cbz or write.delete_all_tags:
            result = self._dump_to_archive(formats)
        logger.info(f"Wrote metadata to: {self._path}")
        return result
