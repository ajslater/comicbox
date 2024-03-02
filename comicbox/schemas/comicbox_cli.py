"""Metadata cli format."""

from logging import getLogger
from types import MappingProxyType

from comicbox.dict_funcs import deep_update
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.pdf import MuPDFTransform

LOG = getLogger(__name__)

_CLI_TRANSFORMS = (
    MuPDFTransform,
    ComictaggerTransform,
    CoMetTransform,
    MetronInfoTransform,
    ComicBookInfoTransform,
    ComicInfoTransform,
    ComicboxJsonTransform,
    ComicboxYamlTransform,
)

CLI_TRANSFORMS_BY_SCHEMA: MappingProxyType[type[BaseSchema], type[BaseTransform]] = (
    MappingProxyType(
        {transform.SCHEMA_CLASS: transform for transform in _CLI_TRANSFORMS}
    )
)


class ComicboxCLISchema(ComicboxYamlSchema):
    """Comicbox CLI YAML Schema."""

    CONFIG_KEYS = frozenset({"cli"})
    FILENAME = "comicbox-cli.yaml"

    class Meta(ComicboxYamlSchema.Meta):
        """Schema Options."""

    def _transform_and_load(self, schema, transform, data, final_dict, *args, **kwargs):
        try:
            if data_dict := schema.load(data, *args, **kwargs):
                comicbox_data = transform.to_comicbox(data_dict)
                deep_update(final_dict, comicbox_data)
                LOG.debug(
                    f"Loaded {len(data_dict)} tags from {self._path}"
                    f" with {schema.__class__.__name__}"
                )
                return True
        except Exception:
            LOG.exception(f"CLI Transform and load with {transform=}")
        return False

    def load(self, data, *args, **kwargs):
        """Deserialize metadata from many schemas."""
        final_dict = {}
        for schema_class, transform_class in CLI_TRANSFORMS_BY_SCHEMA.items():
            try:
                schema = schema_class(path=self._path)
                transform = transform_class(self._path)
                res = self._transform_and_load(
                    schema, transform, data, final_dict, *args, **kwargs
                )
                if not res:
                    wrapped_data = transform.wrap(data)
                    res = self._transform_and_load(
                        schema, transform, wrapped_data, final_dict, *args, **kwargs
                    )
            except Exception as exc:
                LOG.debug(f"schema load {self._path} {schema_class} {exc}")

        return final_dict

    def dumps(self, obj, *args, **kwargs):
        """Dump string as a one liner."""
        return super().dumps(obj, *args, dfs=True, **kwargs)
