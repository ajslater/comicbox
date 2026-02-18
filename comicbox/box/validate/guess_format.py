"""Validate ComiciInfo.xml test files."""

from pathlib import Path
from types import MappingProxyType

from comicbox.formats import MetadataFormats

SUFFIXES = frozenset({"txt", "xml", "json", "yaml", "yml"})
_CBI_STEMS = tuple(
    variation
    for substring in ("comic-book-info", "comic-book-lover")
    for variation in (substring, substring.replace("-", ""))
)
_SUFFIX_SUBSTRINGS = MappingProxyType(
    {
        "json": {
            "comicbox": MetadataFormats.COMICBOX_JSON,
            "pdf": MetadataFormats.PDF,
            "comictagger": MetadataFormats.COMICTAGGER,
            **dict.fromkeys(_CBI_STEMS, MetadataFormats.COMIC_BOOK_INFO),
        },
        "xml": {
            "comicinfo": MetadataFormats.COMIC_INFO,
            "metron": MetadataFormats.METRON_INFO,
            "comet": MetadataFormats.COMET,
            "pdf": MetadataFormats.PDF_XML,
        },
        "yaml": {
            "comicbox": MetadataFormats.COMICBOX_YAML,
        },
        "yml": {
            "comicbox": MetadataFormats.COMICBOX_YAML,
        },
        "txt": {"filename": MetadataFormats.FILENAME},
    }
)


def guess_format(path: Path | str) -> MetadataFormats | None:
    """Guess format by filename."""
    path = Path(path)
    stem = path.stem.lower()
    suffix = path.suffix[1:].lower()

    fmt = None
    fmt_map = _SUFFIX_SUBSTRINGS.get(suffix, {})
    for substring, value in fmt_map.items():
        if substring in stem:
            fmt = value
            break
    else:
        reason = f"Can't guess format for {path} suffix {suffix}"
        raise ValueError(reason)
    return fmt
