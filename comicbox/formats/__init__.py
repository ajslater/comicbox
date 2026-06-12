"""
Metadata formats registry.

Every format is a self-contained package under `comicbox.formats.<name>`
exporting a `REGISTRATION: FormatRegistration` from its `__init__.py`.
This module assembles the `MetadataFormats` enum from those registrations.
"""

from enum import Enum
from types import MappingProxyType

from comicbox.formats._base import FormatRegistration
from comicbox.formats.comet import REGISTRATION as _COMET_REGISTRATION
from comicbox.formats.comic_book_info import (
    REGISTRATION as _COMIC_BOOK_INFO_REGISTRATION,
)
from comicbox.formats.comic_info import REGISTRATION as _COMIC_INFO_REGISTRATION
from comicbox.formats.comicbox import (
    CLI_YAML_REGISTRATION as _COMICBOX_CLI_YAML_REGISTRATION,
)
from comicbox.formats.comicbox import (
    JSON_REGISTRATION as _COMICBOX_JSON_REGISTRATION,
)
from comicbox.formats.comicbox import (
    YAML_REGISTRATION as _COMICBOX_YAML_REGISTRATION,
)
from comicbox.formats.comicvine_api import REGISTRATION as _COMICVINE_API_REGISTRATION
from comicbox.formats.filename import REGISTRATION as _FILENAME_REGISTRATION
from comicbox.formats.metron_api import REGISTRATION as _METRON_API_REGISTRATION
from comicbox.formats.metron_info import REGISTRATION as _METRON_INFO_REGISTRATION
from comicbox.formats.pdf import PDF_REGISTRATION as _PDF_REGISTRATION
from comicbox.formats.pdf import PDF_XML_REGISTRATION as _PDF_XML_REGISTRATION


class MetadataFormats(Enum):
    """Metadata formats."""

    # The order these are listed is the order of masking. Very important.

    FILENAME = _FILENAME_REGISTRATION.format
    PDF = _PDF_REGISTRATION.format
    PDF_XML = _PDF_XML_REGISTRATION.format
    COMET = _COMET_REGISTRATION.format
    COMIC_BOOK_INFO = _COMIC_BOOK_INFO_REGISTRATION.format
    COMIC_INFO = _COMIC_INFO_REGISTRATION.format
    METRON_INFO = _METRON_INFO_REGISTRATION.format
    METRON_API = _METRON_API_REGISTRATION.format
    COMICVINE_API = _COMICVINE_API_REGISTRATION.format
    COMICBOX_YAML = _COMICBOX_YAML_REGISTRATION.format
    COMICBOX_JSON = _COMICBOX_JSON_REGISTRATION.format
    COMICBOX_CLI_YAML = _COMICBOX_CLI_YAML_REGISTRATION.format


# Reverse lookup: enum member → its REGISTRATION. Used by `comicbox.formats.sources`
# to derive source-membership tuples from per-format declarations.
FORMAT_REGISTRATIONS: MappingProxyType[MetadataFormats, FormatRegistration] = (
    MappingProxyType(
        {
            MetadataFormats.FILENAME: _FILENAME_REGISTRATION,
            MetadataFormats.PDF: _PDF_REGISTRATION,
            MetadataFormats.PDF_XML: _PDF_XML_REGISTRATION,
            MetadataFormats.COMET: _COMET_REGISTRATION,
            MetadataFormats.COMIC_BOOK_INFO: _COMIC_BOOK_INFO_REGISTRATION,
            MetadataFormats.COMIC_INFO: _COMIC_INFO_REGISTRATION,
            MetadataFormats.METRON_INFO: _METRON_INFO_REGISTRATION,
            MetadataFormats.METRON_API: _METRON_API_REGISTRATION,
            MetadataFormats.COMICVINE_API: _COMICVINE_API_REGISTRATION,
            MetadataFormats.COMICBOX_YAML: _COMICBOX_YAML_REGISTRATION,
            MetadataFormats.COMICBOX_JSON: _COMICBOX_JSON_REGISTRATION,
            MetadataFormats.COMICBOX_CLI_YAML: _COMICBOX_CLI_YAML_REGISTRATION,
        }
    )
)


def _validate_registrations() -> None:
    """
    Fail at import when the hand-maintained format listings drift.

    The enum and the reverse-lookup map above are maintained by hand from
    the per-package REGISTRATIONs; without this check a sync mistake
    (missing entry, mismatched registration, config-key collision)
    degrades silently into wrong masking order or wrong format selection
    instead of an immediate error.
    """
    seen_keys: dict[str, str] = {}
    for member in MetadataFormats:
        registration = FORMAT_REGISTRATIONS.get(member)
        if registration is None:
            reason = f"FORMAT_REGISTRATIONS is missing {member.name}"
            raise RuntimeError(reason)
        if registration.format is not member.value:
            reason = (
                f"FORMAT_REGISTRATIONS[{member.name}] holds a different "
                "registration than the enum value was built from"
            )
            raise RuntimeError(reason)
        for key in member.value.config_keys:
            if (other := seen_keys.get(key)) is not None:
                reason = (
                    f"config key {key!r} is claimed by both {other} and {member.name}"
                )
                raise RuntimeError(reason)
            seen_keys[key] = member.name


_validate_registrations()
