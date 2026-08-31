"""Validate methods."""

import sys
from pathlib import Path
from types import MappingProxyType

from loguru import logger

from comicbox.box.dump_files import ComicboxDumpToFiles
from comicbox.box.init import SourceData
from comicbox.box.validate.guess_format import guess_format
from comicbox.exceptions import MetadataError
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


class ComicboxValidate(ComicboxDumpToFiles):
    """Validate Methods."""

    def validate(self):
        """Validate metadata in archive."""
        if not self._config.print.validate:
            return

        validated = True
        for source in MetadataSources:
            if source_data_list := self.get_source_metadata(source):
                for source_data in source_data_list:
                    validated &= validate_source(source_data)
        if not validated:
            logger.error("Metadata validation failed")
            sys.exit(1)
        logger.success("Metadata validation succeeded")
