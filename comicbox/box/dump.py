"""Writing Methods."""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from loguru import logger

from comicbox.box.archive.tag_names import ALL_ARCHIVE_METADATA_FILENAMES
from comicbox.box.pages import ComicboxPages
from comicbox.exceptions import UnparsedTagFileError
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import EXT_KEY, ComicboxSchemaMixin
from comicbox.formats.pdf.schema import MuPDFSubSchema
from comicbox.formats.sources import MetadataSources
from comicbox.merge import AdditiveMerger

ARCHIVE_FORMATS = frozenset(
    MetadataSources.ARCHIVE_FILE.value.formats
    + MetadataSources.ARCHIVE_COMMENT.value.formats
)
# The formats a write puts into an archive: its tag files, its comment, and a
# PDF's own metadata.
_WRITABLE_FORMATS = frozenset({*ARCHIVE_FORMATS, MetadataFormats.PDF})
# Where -m and --import values come from, and where a comic's own come from.
_GIVEN_SOURCES = (MetadataSources.IMPORT_FILE, MetadataSources.CLI)
_ARCHIVE_SOURCES = (
    MetadataSources.ARCHIVE_FILENAME,
    MetadataSources.ARCHIVE_PDF,
    MetadataSources.ARCHIVE_COMMENT,
    MetadataSources.ARCHIVE_FILE,
)
ROOT_TAG = ComicboxSchemaMixin.ROOT_TAG


def _holds(have: Any, want: Any) -> bool:
    """Tell whether a value read back holds one given: each key, item and value."""
    if isinstance(want, Mapping):
        return isinstance(have, Mapping) and all(
            _holds(have.get(key), value) for key, value in want.items()
        )
    if isinstance(want, list | tuple | set | frozenset):
        return isinstance(have, list | tuple | set | frozenset) and all(
            any(_holds(item, wanted) for item in have) for wanted in want
        )
    return have == want


# Every field -w pdf maps, empty: what a PDF write that no longer has it sets.
# A field it does not map, such as the creation date, is never sent.
_CLEARED_PDF_METADATA = MappingProxyType(
    {field.data_key or name: "" for name, field in MuPDFSubSchema().fields.items()}
)
_UNPARSED = "it could not be parsed"
# Tag files are written in the order the formats are declared.
_FORMAT_ORDER = MappingProxyType(
    {fmt: index for index, fmt in enumerate(MetadataFormats)}
)


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
        return self._config.write.formats | carried.formats

    def get_write_formats(self) -> frozenset[MetadataFormats] | None:
        """
        Get the formats a write of this comic writes, as ``dump`` decides them.

        Under ``keep``, the formats named and every tag format the comic
        carries that was read. None when nothing is to be written.
        """
        return self._get_dump_formats()

    def _get_carried_formats_for_cbz(self) -> frozenset[MetadataFormats]:
        """
        Get the formats --cbz without -w writes back: those the archive carried.

        Its tag files, its ComicBookInfo comment and a PDF's own metadata;
        -m and --import values merge into them. Every loaded format was
        written, so -m added a comicbox-cli.yaml the comic never had.
        """
        carried = self.get_carried_formats().formats
        if not carried and self._has_given_metadata():
            logger.warning(
                f"{self._path} carries no tag format: without -w, the metadata"
                " given with -m or --import has nowhere to be written."
            )
        return carried

    def _has_given_metadata(self) -> bool:
        """Tell whether metadata came from -m, --import or the API caller."""
        general, convert = self._config.general, self._config.convert
        return bool(
            general.metadata_cli
            or convert.import_paths
            or self._sources.get(MetadataSources.API)
        )

    def _is_cbz_alone(self) -> bool:
        """Tell whether this is a --cbz write naming no format."""
        write = self._config.write
        return bool(
            self._config.convert.cbz
            and not write.formats
            and not write.keep_formats
            and not write.delete_all_tags
        )

    def _dump_carried_format(
        self,
        fmt: MetadataFormats,
        schema: Any,
        denormalized_metadata: Mapping,
        files: dict[str, Mapping],
        comment: dict[str, bytes | None],
    ) -> None:
        """
        Write a format --cbz carries over: a ComicBookInfo comment as a comment.

        It came back as a comic-book-info.json file. A tag file is written as
        any write writes it.
        """
        in_comment = self.get_carried_formats().in_comment
        if fmt in MetadataSources.ARCHIVE_COMMENT.value.formats and in_comment:
            comment["c"] = schema.dumps(denormalized_metadata).encode(errors="replace")
            filename = fmt.value.filename.lower()
            if not any(Path(name).name.lower() == filename for name in self.namelist()):
                return
        _dump_format(fmt, schema, denormalized_metadata, files, comment)

    def _get_dump_formats(self) -> frozenset[MetadataFormats] | None:
        write = self._config.write
        convert = self._config.convert
        formats: frozenset[MetadataFormats] | None = frozenset()
        if write.keep_formats:
            formats = self._get_keep_formats()
        elif write.formats:
            formats = write.formats
        elif convert.cbz:
            formats = self._get_carried_formats_for_cbz()
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

        Only for a PDF: an untagged comic of any other kind gains no tag file
        from --cbz. Under keep, also never over a ComicInfo the archive
        carries and the read configuration did not read: keep replaces no
        tag file it did not read.
        """
        if not self._archive_is_pdf:
            return False
        if not self._config.write.keep_formats:
            return True
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
        if fmt not in _WRITABLE_FORMATS:
            # -w pdf returned here, never reaching the PDF branch below.
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
        elif self._is_cbz_alone():
            self._dump_carried_format(
                fmt, schema, denormalized_metadata, files, comment
            )
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
            # In one fixed order: a frozenset's follows the hash seed.
            for fmt in sorted(formats, key=_FORMAT_ORDER.__getitem__):
                self._dump_format_to_archive(fmt, files, pdf_md, comment)

        if self._writes_pdf_metadata(formats):
            # pymupdf leaves a key it is not given: an empty value clears it.
            pdf_md = {**_CLEARED_PDF_METADATA, **pdf_md}
        # write to the archive, then re-seed caches from the new bytes.
        self.write_archive_metadata(files, comment["c"], pdf_md)
        self._reset_caches_after_write()

    def _writes_pdf_metadata(self, formats: frozenset[MetadataFormats]) -> bool:
        """
        Tell whether this write sets a PDF's own metadata in place.

        It does under -w pdf, and under keep for a PDF that has some; and
        --delete-all-tags clears it. A field it maps that the metadata no
        longer has is then cleared, as a zip write drops a tag file.
        """
        if not self._archive_is_pdf or self._config.convert.cbz:
            return False
        return self._config.write.delete_all_tags or MetadataFormats.PDF in formats

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
        return self._write_formats(formats)

    def _write_formats(self, formats: frozenset[MetadataFormats]) -> None:
        """Write the formats decided, or say there is nothing to keep."""
        write = self._config.write
        writes = bool(formats or self._config.convert.cbz or write.delete_all_tags)
        if write.keep_formats and not writes:
            # Not a failure: there is just nothing to keep, and none named.
            logger.info(f"Nothing to keep in {self._path}: not writing it.")
            return None
        result = self._dump_to_archive(formats) if writes else None
        logger.info(f"Wrote metadata to: {self._path}")
        if formats and self._is_cbz_alone():
            self._warn_of_unwritten_patch_values()
        return result

    def _merged_sources(self, sources: tuple[MetadataSources, ...]) -> dict:
        merged: dict = {}
        for source in sources:
            for loaded in self.get_normalized_metadata(source) or ():
                AdditiveMerger.merge(merged, dict(loaded.metadata.get(ROOT_TAG) or {}))
        return merged

    def _warn_of_unwritten_patch_values(self) -> None:
        """
        Name the -m and --import keys a --cbz without -w had nowhere to write.

        Their values go only into the formats the comic carried, and a format
        can have no place for one: MetronInfo for a title apart from its
        stories, CoMet for tags. What the comic reads back after the write
        shows which landed; -w names a format that holds the rest.
        """
        given = self._merged_sources(_GIVEN_SOURCES)
        if not given:
            return
        held = self._merged_sources(_ARCHIVE_SOURCES)
        if missing := sorted(
            key for key, value in given.items() if not _holds(held.get(key), value)
        ):
            logger.warning(
                f"{self._path}: the formats it carries have no place for"
                f" {', '.join(missing)} from -m or --import, so they were not"
                " written. Name a format that holds them with -w."
            )

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
