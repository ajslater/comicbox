"""The names of the tag files an archive can carry, in lower case."""

from comicbox.formats.sources import MetadataSources

ALL_ARCHIVE_METADATA_FILENAMES = frozenset(
    {
        fmt.value.filename.lower()
        for fmt in MetadataSources.ARCHIVE_FILE.value.formats
        if fmt.value.enabled
    }
)
