"""Identity transforms for comicbox's own reading-list serializations."""

import sys
from collections.abc import Mapping
from typing import Any

from comicbox.readinglists.changes import quote_value
from comicbox.readinglists.schema import (
    READING_LIST_KEY,
    ReadingListJsonSchema,
    ReadingListYamlSchema,
)
from comicbox.readinglists.transform import ReadingListTransform

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


# The keys a native document's root may hold: the list, and the JSON
# schema's id comicbox writes beside it.
_ROOT_KEYS = frozenset({READING_LIST_KEY, "schema"})


class _NativeTransform(ReadingListTransform):
    """A format whose schema is the model's."""

    @override
    def load_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Hand the list to the model, which names its drops; name the rest."""
        self.warnings.extend(
            f"{key}: {quote_value(value)} dropped"
            for key, value in document.items()
            if key not in _ROOT_KEYS
        )
        return dict(document)


class ReadingListYamlTransform(_NativeTransform):
    """Comicbox reading-list YAML."""

    SCHEMA_CLASS = ReadingListYamlSchema


class ReadingListJsonTransform(_NativeTransform):
    """Comicbox reading-list JSON."""

    SCHEMA_CLASS = ReadingListJsonSchema
