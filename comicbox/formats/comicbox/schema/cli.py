"""Metadata cli format."""

import sys
from types import MappingProxyType
from typing import Any

from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


class ComicboxCLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    @override
    def dumps(
        self,
        obj: dict[str, Any] | MappingProxyType[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Dump string as a one liner."""
        return super().dumps(obj, *args, dfs=True, **kwargs)
