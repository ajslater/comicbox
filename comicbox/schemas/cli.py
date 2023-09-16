"""Metadata cli format."""
from logging import getLogger

from comicbox.schemas.comet import CoMetSchema
from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicinfo import ComicInfoSchema
from comicbox.schemas.comictagger import ComictaggerSchema
from comicbox.schemas.json import ComicboxJsonSchema
from comicbox.schemas.pdf import PDFSchema
from comicbox.schemas.yaml import ComicboxYamlSchema

LOG = getLogger(__name__)


class CLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    CONFIG_KEYS = frozenset({"cli"})
    FILENAME = "comicbox-cli.yaml"
    _SCHEMAS = (
        PDFSchema,
        CoMetSchema,
        ComicBookInfoSchema,
        ComicInfoSchema,
        ComictaggerSchema,
        ComicboxJsonSchema,
        ComicboxYamlSchema,
    )

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    def load(self, data, *args, **kwargs):
        """Deserialize metadata from every schema style."""
        final_dict = {}
        for schema_class in self._SCHEMAS:
            try:
                schema = schema_class(self._path)
                if data_dict := schema.load(data, *args, **kwargs):
                    final_dict.update(data_dict)
                    LOG.debug(
                        f"Loaded {len(data_dict)} tags from {self._path}"
                        f" with {schema_class.__name__}"
                    )
            except Exception as exc:
                LOG.debug(f"schema load {self._path} {schema_class} {exc}")

        return final_dict

    def dumps(self, data, *args, **kwargs):
        """Dump string as a one liner."""
        return super().dumps(data, *args, dfs=True, **kwargs)
