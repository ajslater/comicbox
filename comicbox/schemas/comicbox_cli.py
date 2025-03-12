"""Metadata cli format."""

from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema


class ComicboxCLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    CONFIG_KEYS = frozenset({"cli"})
    FILENAME = "comicbox-cli.yaml"

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    def dumps(self, obj, *args, **kwargs):
        """Dump string as a one liner."""
        return super().dumps(obj, *args, dfs=True, **kwargs)
