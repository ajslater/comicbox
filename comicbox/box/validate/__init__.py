"""Validate methods."""

from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from loguru import logger

from comicbox.box.dump_files import ComicboxDumpToFiles
from comicbox.box.init import SourceData
from comicbox.box.validate.guess_format import guess_format
from comicbox.exceptions import MetadataError, ValidationFailedError
from comicbox.formats import FORMAT_REGISTRATIONS, MetadataFormats
from comicbox.formats.sources import MetadataSources
from comicbox.validate.spec import build_validator, validation_failure_exceptions

#: Derived from per-format `REGISTRATION.validator_spec`. Formats whose
#: registration has `validator_spec=None` (PDF, PDF_XML, Filename, online
#: APIs) are absent here and trigger the "no validator available" path
#: below. The specs stay unbuilt: `build_validator()` compiles a schema
#: the first time this opt-in path actually validates against it.
FMT_VALIDATOR_SPEC_MAP = MappingProxyType(
    {
        fmt: registration.validator_spec
        for fmt, registration in FORMAT_REGISTRATIONS.items()
        if registration.validator_spec is not None
    }
)


def validate_source(
    data: SourceData | str | bytes | Path | None = None,
    fmt: MetadataFormats | None = None,
) -> bool:
    """Validate a metadata file from disk."""
    if isinstance(data, SourceData):
        if data.fmt:
            fmt = data.fmt
        elif data.path:
            fmt = guess_format(data.path)
        data = data.data  # pyright: ignore[reportAssignmentType], # ty: ignore[invalid-assignment]
    elif not fmt and isinstance(data, Path):
        fmt = guess_format(data)

    if not fmt:
        reason = "Cannot determine format for source. Can't validate."
        raise MetadataError(reason)

    spec = FMT_VALIDATOR_SPEC_MAP.get(fmt)
    if not spec:
        # Just pass formats without validators
        logger.warning(f"{fmt.value.label}: no validator available")
        return True
    validator = build_validator(spec)
    try:
        validator.validate(data)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        logger.info(f"{fmt.value.label}: data validated")
        result = True
    except validation_failure_exceptions() as exc:
        logger.warning(f"{fmt.value.label}: failed validation")
        logger.warning(exc)
        result = False
    return result


def _names_comic_book_info(comment: object) -> bool:
    """
    Tell a comment that is, or means to be, ComicBookInfo: it holds its key.

    Free text is not validated, but a comment with the ComicBookInfo key
    that does not parse is a broken tag, and fails.
    """
    from comicbox.formats.comic_book_info.schema import ComicBookInfoSchema

    if isinstance(comment, bytes):
        comment = comment.decode(errors="replace")
    return isinstance(comment, str) and ComicBookInfoSchema.ROOT_DATA_KEY in comment


def _validated_format(
    source: MetadataSources, source_data: SourceData
) -> MetadataFormats | None:
    """
    Get the format to validate a source as, or None when it is not one.

    -m metadata, an API string and an import whose name says no format
    have no format to check against, and an archive comment without the
    ComicBookInfo key is free text: each is logged and passed over, not
    failed.
    """
    label = source.value.label
    if source == MetadataSources.ARCHIVE_COMMENT and not _names_comic_book_info(
        source_data.data
    ):
        logger.info(f"{label}: not ComicBookInfo, not validated")
        return None
    if source_data.fmt:
        return source_data.fmt
    if source_data.path and str(source_data.path) not in ("", "."):
        with suppress(MetadataError):
            return guess_format(source_data.path)
    logger.info(f"{label}: format unknown, not validated")
    return None


class ComicboxValidate(ComicboxDumpToFiles):
    """Validate Methods."""

    def validate(self):
        """Validate metadata in archive."""
        if not self._config.print.validate:
            return

        validated = True
        for source in MetadataSources:
            for source_data in self.get_source_metadata(source) or ():
                if fmt := _validated_format(source, source_data):
                    validated &= validate_source(replace(source_data, fmt=fmt))
        if not validated:
            # Raised, not exited: the Runner fails this file and goes on.
            reason = f"{self._path}: metadata validation failed"
            raise ValidationFailedError(reason)
        logger.success("Metadata validation succeeded")
