"""Metadata cli format."""

from types import MappingProxyType
from typing import Any

from typing_extensions import override

from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema


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
