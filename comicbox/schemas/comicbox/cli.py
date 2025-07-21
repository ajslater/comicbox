"""Metadata cli format."""

from typing_extensions import override

from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema


class ComicboxCLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    @override
    def dumps(self, obj, *args, **kwargs):
        """Dump string as a one liner."""
        return super().dumps(obj, *args, dfs=True, **kwargs)
