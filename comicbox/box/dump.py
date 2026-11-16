"""Writing Methods."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from comicbox.box.archive.write import ALL_ARCHIVE_METADATA_FILENAMES
from comicbox.box.pages import ComicboxPages
from comicbox.exceptions import UnparsedTagFileError
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import EXT_KEY
from comicbox.formats.sources import MetadataSources

ARCHIVE_FORMATS = frozenset(
    MetadataSources.ARCHIVE_FILE.value.formats
    + MetadataSources.ARCHIVE_COMMENT.value.formats
)
# comicbox cannot write a PDF's own metadata (_dump_format_to_archive
# returns before its branch), so keep has nothing to write for it.
_KEEP_UNWRITABLE = frozenset({MetadataFormats.PDF})
_UNPARSED = "it could not be parsed"


def _without_filename_only_keys(schema, denormalized_metadata: Mapping) -> Mapping:
    """
    Drop keys that describe the file's name rather than its contents.

    ``ext`` is parsed from the filename and means nothing inside the
    archive — but a metadata file written into a *converted* archive is
    built before the suffix changes, so it would preserve the old one
    ("ext: cbt" inside a .cbz). Read back, that stale value outranks the
    real filename and can rename the archive to a format it isn't.
    """
    root_tag = getattr(schema, "ROOT_TAG", None)
    sub_md = denormalized_metadata.get(root_tag) if root_tag else None
    if not isinstance(sub_md, Mapping) or EXT_KEY not in sub_md:
        return denormalized_metadata
    stripped = dict(denormalized_metadata)
    stripped[root_tag] = {key: value for key, value in sub_md.items() if key != EXT_KEY}
    return stripped


def _dump_format(
    fmt: MetadataFormats,
    schema: Any,
    denormalized_metadata: Mapping,
    files: dict[str, Mapping],
    comment: dict[str, bytes | None],
) -> None:
    """Write a format as a file under its own name, or as the comment."""
    if fmt in MetadataSources.ARCHIVE_FILE.value.formats:
        files[fmt.value.filename] = schema.dumps(
            _without_filename_only_keys(schema, denormalized_metadata)
        )
    elif fmt in MetadataSources.ARCHIVE_COMMENT.value.formats:
        cmnt = schema.dumps(denormalized_metadata)
        cmnt = cmnt.encode(errors="replace")
        comment["c"] = cmnt


class ComicboxDump(ComicboxPages):
    """Writing Methods."""

    def _get_keep_formats(self) -> frozenset[MetadataFormats]:
        """
        Get what a ``keep`` write writes: the formats named and those carried.

        A tag file the comic carries that did not parse refuses the write:
        what was read from the rest would be written without it.
        """
        carried = self.get_carried_formats()
        if carried.unreadable:
            names = ", ".join(carried.unreadable)
            reason = (
                f"Not writing {self._path}: its {names} could not be parsed,"
                " so keep cannot keep it."
            )
            raise UnparsedTagFileError(reason)
        return (self._config.write.formats | carried.formats) - _KEEP_UNWRITABLE

    def get_write_formats(self) -> frozenset[MetadataFormats] | None:
        """
        Get the formats a write of this comic writes, as ``dump`` decides them.

        Under ``keep``, the formats named and every tag format the comic
        carries that was read. None when nothing is to be written.
        """
        return self._get_dump_formats()

    def _get_loaded_formats(self) -> frozenset[MetadataFormats]:
        """Get every format loaded, from any source: what --cbz writes back."""
        loaded_data_lists = (
            self.get_loaded_metadata(source) for source in MetadataSources
        )
        return frozenset(
            loaded_data.fmt
            for loaded_data_list in loaded_data_lists
            if loaded_data_list
            for loaded_data in loaded_data_list
            if loaded_data and loaded_data.fmt is not None
        )

    def _get_dump_formats(self) -> frozenset[MetadataFormats] | None:
        write = self._config.write
        convert = self._config.convert
        formats: frozenset[MetadataFormats] | None = frozenset()
        if write.keep_formats:
            formats = self._get_keep_formats()
        elif write.formats:
            formats = write.formats
        elif convert.cbz:
            formats = self._get_loaded_formats()
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
        if self._config.convert.cbz and self._defaults_to_comic_info():
            formats_without_pdf = formats - {MetadataFormats.PDF}
            if not formats_without_pdf:
                logger.info(
                    "PDF→CBZ conversion with no --write formats; "
                    "defaulting to ComicInfo."
                )
                formats = frozenset(formats_without_pdf | {MetadataFormats.COMIC_INFO})
        return formats

    def _defaults_to_comic_info(self) -> bool:
        """
        Whether the PDF to CBZ default may add ComicInfo.

        Under keep, only for a PDF, and never over a ComicInfo the archive
        carries and the read configuration did not read: keep replaces no
        tag file it did not read, and an untagged comic gains none.
        """
        if not self._config.write.keep_formats:
            return True
        if not self._archive_is_pdf:
            return False
        unread = MetadataFormats.COMIC_INFO not in self.get_carried_formats().formats
        filename = MetadataFormats.COMIC_INFO.value.filename.lower()
        return not (
            unread
            and any(Path(name).name.lower() == filename for name in self.namelist())
        )

    def _dump_format_to_archive(
        self,
        fmt: MetadataFormats,
        files: dict[str, Mapping],
        pdf_md: dict,
        comment: dict[str, bytes | None],
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
            # fmt is PDF here, so the pair above is already the PDF pair.
            mupdf_md = schema.dump(denormalized_metadata) or {}
            if isinstance(mupdf_md, Mapping):
                pdf_md.update(mupdf_md.get(schema.ROOT_TAG, {}))
        elif self._config.write.keep_formats:
            self._dump_kept_format(fmt, schema, denormalized_metadata, files, comment)
        else:
            _dump_format(fmt, schema, denormalized_metadata, files, comment)

    def _dump_kept_format(
        self,
        fmt: MetadataFormats,
        schema: Any,
        denormalized_metadata: Mapping,
        files: dict[str, Mapping],
        comment: dict[str, bytes | None],
    ) -> None:
        """
        Write a format under keep wherever the comic carries it.

        A ComicBookInfo comment stays a comment, and a file is written back
        at every member path that bears its name, read or not: the write
        removes each of them, and no copy may be left stale to win the next
        read. A format the comic does not carry is written as any write
        writes it.
        """
        written = False
        in_comment = self.get_carried_formats().in_comment
        if fmt in MetadataSources.ARCHIVE_COMMENT.value.formats and in_comment:
            comment["c"] = schema.dumps(denormalized_metadata).encode(errors="replace")
            written = True
        filename = fmt.value.filename.lower()
        for path in self.namelist():
            if Path(path).name.lower() != filename:
                continue
            files[path] = schema.dumps(
                _without_filename_only_keys(schema, denormalized_metadata)
            )
            written = True
        if not written:
            _dump_format(fmt, schema, denormalized_metadata, files, comment)

    def _dump_to_archive(self, formats: frozenset[MetadataFormats]) -> None:
        """Prepare archive files and comment and write to archive."""
        self._warn_of_unparsed_tag_files(formats)
        # Get files and comment. Under keep, a comment not rewritten is kept:
        # None leaves it as it is.
        files = {}
        comment: dict[str, bytes | None] = {
            "c": None if self._config.write.keep_formats else b""
        }
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
        write, but the sources that never came from the file can't be
        rebuilt by re-reading it: the caller-injected API metadata, and
        whatever the online lookup fetched. The lookup is once-per-box
        (``_online_lookup_done_flag`` outlives this reset), so dropping
        its sources here left the post-write rename — and any other
        read after a write — deciding on pre-online metadata, minus
        whatever the written formats happened to carry back.

        Lives here rather than in the archive write layer so file I/O
        stays decoupled from the source-cache lifecycle.
        """
        keep_sources = {
            source: source_data_list
            for source in self.SOURCES_SET_ELSEWHERE
            if (source_data_list := self._sources.get(source))
        }
        self._reset_archive(None, None, keep_sources)

    def _is_write_disabled(self) -> bool:
        """Return whether the config asks for no write at all."""
        write = self._config.write
        return self._config.general.dry_run or not (
            write.formats
            or write.keep_formats
            or self._config.convert.cbz
            or write.delete_all_tags
        )

    def dump(self, formats: frozenset[MetadataFormats] | None = None) -> None:
        """Write metadata according to config.write settings."""
        write = self._config.write
        convert = self._config.convert
        if self._is_write_disabled():
            logger.info(f"Not writing metadata for: {self._path}")
            return None

        if self._path:
            # Refuse an occupied conversion destination before any metadata
            # is read. _get_dump_formats() below loads and merges every
            # source, which is the expensive part of a write that was only
            # ever going to be refused -- a kept-original CBR whose CBZ twin
            # already exists is the common case, and it reaches here from
            # the CLI as well as the API. _create_zipfile repeats the check
            # (it is idempotent) so direct callers stay guarded.
            self._get_new_archive_path()

        # Must get metadata *before* get write formats
        if formats is None:
            formats = self._get_dump_formats()
            if formats is None:
                return None

        writes = bool(formats or convert.cbz or write.delete_all_tags)
        if write.keep_formats and not writes:
            # Not a failure: there is just nothing to keep, and none named.
            logger.info(f"Nothing to keep in {self._path}: not writing it.")
            return None
        result = self._dump_to_archive(formats) if writes else None
        logger.info(f"Wrote metadata to: {self._path}")
        return result

    def _warn_of_unparsed_tag_files(self, formats: frozenset[MetadataFormats]) -> None:
        """
        Name each tag file that did not parse and that this write takes away.

        Without keep, a write replaces or removes every tag file the comic
        has; one that could not be parsed added nothing to what is written.
        Keep refuses such a comic instead, and deleting all tags means it.
        """
        write = self._config.write
        if write.keep_formats or write.delete_all_tags:
            return
        written = {fmt.value.filename.lower() for fmt in formats}
        for name in self.get_carried_formats().unreadable:
            if name.lower() not in ALL_ARCHIVE_METADATA_FILENAMES:
                continue
            if name.lower() in written:
                why = "so nothing it held is in the new one"
                logger.warning(f"Replacing {name} in {self._path}: {_UNPARSED}, {why}.")
            else:
                why = "and its format is not one written"
                logger.warning(
                    f"Removing {name} from {self._path}: {_UNPARSED}, {why}."
                )
