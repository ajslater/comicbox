"""
Metadata sources definitions.

`MetadataSources` is assembled dynamically from `_SOURCE_DEFINITIONS`
plus per-format `REGISTRATION.sources` declarations. Each format
declares which sources it belongs to (and at what masking priority);
the central enum's format tuples are derived rather than hand-written.

Trade-off: pyright/mypy do not statically see the enum members. Typo'd
`MetadataSources.NOSUCH` raises `AttributeError` at runtime instead of
being flagged at type-check time. Acceptable because all consumers are
internal and the source taxonomy is stable (~10 entries).
"""

from dataclasses import dataclass
from enum import Enum

from comicbox.formats import FORMAT_REGISTRATIONS, MetadataFormats


@dataclass
class MetadataSource:
    """Metadata source attributes."""

    label: str
    formats: tuple[MetadataFormats, ...] = tuple(
        fmt for fmt in MetadataFormats if fmt.value.enabled
    )
    from_archive: bool = False


# Source order = source-level masking precedence. Fourth field marks
# sources that accept arbitrary enabled formats (today: IMPORT_FILE for
# the `--import` CLI option, where the file's format is detected at
# read time).
#: Source definition rows: (enum_member_name, label, from_archive, accepts_any_format).
_SOURCE_DEFINITIONS: tuple[tuple[str, str, bool, bool], ...] = (
    ("CONFIG", "Config", False, False),
    ("ARCHIVE_FILENAME", "Filename", True, False),
    ("ARCHIVE_PDF", "Archive Header", True, False),
    ("ARCHIVE_COMMENT", "Archive Comment", True, False),
    ("ARCHIVE_FILE", "Archive File", True, False),
    ("METRON_API", "Metron API", False, False),
    ("COMICVINE_API", "ComicVine API", False, False),
    ("IMPORT_FILE", "Imported File", False, True),
    ("CLI", "Comicbox CLI", False, False),
    ("API", "API", False, False),
)


def _formats_for_source(name: str) -> tuple[MetadataFormats, ...]:
    """
    Collect formats whose REGISTRATION declares membership in this source.

    Sorts by per-source priority (declared in `REGISTRATION.sources[name]`).
    """
    pairs = [
        (priority, fmt)
        for fmt, registration in FORMAT_REGISTRATIONS.items()
        if (priority := registration.sources.get(name)) is not None
    ]
    return tuple(fmt for _, fmt in sorted(pairs, key=lambda p: p[0]))


def _build_source(
    name: str, label: str, from_archive: bool, accepts_any: bool
) -> MetadataSource:  # noqa: FBT001
    if accepts_any:
        return MetadataSource(label, from_archive=from_archive)
    return MetadataSource(
        label,
        formats=_formats_for_source(name),
        from_archive=from_archive,
    )


MetadataSources = Enum(  # pyright: ignore[reportCallIssue]
    "MetadataSources",
    {
        name: _build_source(name, label, from_archive, accepts_any)
        for name, label, from_archive, accepts_any in _SOURCE_DEFINITIONS
    },
)
