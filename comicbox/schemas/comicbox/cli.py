"""Metadata cli format."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

    import comicbox.transforms.comicbox.cli

from typing_extensions import override

from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema


class ComicboxCLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    @override
    def dumps(self: "comicbox.transforms.comicbox.cli.ComicboxCLISchema", obj: "types.MappingProxyType[str, dict[str, dict[str, dict[str, str]|str]]]", *args: None, **kwargs: None) -> str:
        """Dump string as a one liner."""
        return super().dumps(obj, *args, dfs=True, **kwargs)
