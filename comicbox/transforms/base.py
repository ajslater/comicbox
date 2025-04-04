"""Transform to and from a format and comicbox format."""

from collections.abc import Mapping
from types import MappingProxyType

from glom import glom

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    SPECS_TO = MappingProxyType({})
    SPECS_FROM = MappingProxyType({})

    def __init__(self, path=None):
        """Initialize instances."""
        self._path = path
        self._schema = self.SCHEMA_CLASS(path=path)

    @staticmethod
    def _swap_data_key(swap_data_key: bool, schema: BaseSchema, transformed_data: dict):
        """Hack for ComicBookInfo's root key with special characters."""
        if (
            swap_data_key
            and schema.ROOT_DATA_KEY
            and (root := transformed_data.pop(schema.ROOT_TAG, None))
        ):
            transformed_data[schema.ROOT_DATA_KEY] = root

    @classmethod
    def _transform(
        cls,
        spec: Mapping,
        schema: BaseSchema,
        data: Mapping,
        swap_data_key: bool,
    ) -> MappingProxyType:
        """Transform formats to and from normalized Comicbox schema."""
        transformed_data = glom(dict(data), dict(spec))
        cls._swap_data_key(swap_data_key, schema, transformed_data)
        loaded_data = schema.load(transformed_data)
        return MappingProxyType(loaded_data)  # type: ignore[reportAssignmentType]

    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data to a normalized comicbox schema."""
        schema = ComicboxYamlSchema(path=self._path)
        return self._transform(self.SPECS_TO, schema, data, swap_data_key=False)

    def from_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data from the comicbox schema to this schema."""
        schema = self._schema
        return self._transform(
            self.SPECS_FROM,
            schema,
            data,
            swap_data_key=True,
        )
