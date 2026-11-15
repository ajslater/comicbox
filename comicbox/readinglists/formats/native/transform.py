"""Identity transforms for comicbox's own reading-list serializations."""

from comicbox.readinglists.schema import ReadingListJsonSchema, ReadingListYamlSchema
from comicbox.readinglists.transform import ReadingListTransform


class ReadingListYamlTransform(ReadingListTransform):
    """Comicbox reading-list YAML."""

    SCHEMA_CLASS = ReadingListYamlSchema


class ReadingListJsonTransform(ReadingListTransform):
    """Comicbox reading-list JSON."""

    SCHEMA_CLASS = ReadingListJsonSchema
