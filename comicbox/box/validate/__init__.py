"""Validate methods."""

import sys
from pathlib import Path
from types import MappingProxyType

from jsonschema.exceptions import (
    FormatError,
    SchemaError,
    UndefinedTypeCheck,
    UnknownType,
    ValidationError,
)
from loguru import logger
from xmlschema.exceptions import XMLSchemaException

from comicbox.box.dump_files import ComicboxDumpToFiles
from comicbox.box.init import SourceData
from comicbox.box.validate.guess_format import guess_format
from comicbox.box.validate.json_validator import JsonValidator
from comicbox.box.validate.xml_validator import XmlValidator
from comicbox.box.validate.yaml_validator import YamlValidator
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources

FMT_VALIDATOR_MAP = MappingProxyType(
    {
        MetadataFormats.COMIC_INFO: XmlValidator("ComicInfo-v2.1-Draft.xsd"),
        MetadataFormats.COMIC_BOOK_INFO: JsonValidator(
            "comic-book-info-v1.0.schema.json"
        ),
        MetadataFormats.METRON_INFO: XmlValidator("MetronInfo-v1.0.xsd"),
        MetadataFormats.COMET: XmlValidator("CoMet-v1.1.xsd"),
        MetadataFormats.COMICBOX_JSON: JsonValidator("v2.0/comicbox-v2.0.schema.json"),
        MetadataFormats.COMICBOX_YAML: YamlValidator("v2.0/comicbox-v2.0.schema.json"),
        MetadataFormats.COMICBOX_CLI_YAML: YamlValidator(
            "v2.0/comicbox-v2.0.schema.json"
        ),
        # "comictagger":
        # "pdf":
        # "pdfxml":
        # "filename":
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
        raise ValueError(reason)

    validator = FMT_VALIDATOR_MAP.get(fmt)
    if not validator:
        # Just pass formats without validators
        logger.warning(f"{fmt.value.label}: no validator available")
        return True
    try:
        validator.validate(data)  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        logger.info(f"{fmt.value.label}: data validated")
        result = True
    except (
        XMLSchemaException,
        # JsonValidation Errors
        ValidationError,
        SchemaError,
        UndefinedTypeCheck,
        UnknownType,
        FormatError,
    ) as exc:
        logger.warning(f"{fmt.value.label}: failed validation")
        logger.warning(exc)
        result = False
    return result


class ComicboxValidate(ComicboxDumpToFiles):
    """Validate Methods."""

    def validate(self):
        """Validate metadata in archive."""
        if not self._config.validate:
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
