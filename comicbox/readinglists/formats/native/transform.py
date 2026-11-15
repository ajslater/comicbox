"""Identity transforms for comicbox's own reading-list serializations."""

import sys
from collections.abc import Mapping
from typing import Any

from comicbox.readinglists.schema import ReadingListJsonSchema, ReadingListYamlSchema
from comicbox.readinglists.transform import ReadingListTransform

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


class _NativeTransform(ReadingListTransform):
    """A format whose schema is the model's."""

    @override
    def load_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Hand the document to the model as it is; the model names its drops."""
        return dict(document)


class ReadingListYamlTransform(_NativeTransform):
    """Comicbox reading-list YAML."""

    SCHEMA_CLASS = ReadingListYamlSchema


class ReadingListJsonTransform(_NativeTransform):
    """Comicbox reading-list JSON."""

    SCHEMA_CLASS = ReadingListJsonSchema
