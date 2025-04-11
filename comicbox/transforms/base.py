"""Transform to and from a format and comicbox format."""

from collections.abc import Mapping
from types import MappingProxyType

from glom import glom

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema


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
    def _swap_data_key(schema: BaseSchema, transformed_data: dict):
        """Hack for ComicBookInfo's root key with special characters."""
        if schema.ROOT_DATA_KEY and (
            root := transformed_data.pop(schema.ROOT_TAG, None)
        ):
            transformed_data[schema.ROOT_DATA_KEY] = root

    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data to a normalized comicbox schema."""
        schema = ComicboxYamlSchema(path=self._path)
        transformed_data = glom(dict(data), dict(self.SPECS_TO), glom_debug=True)
        loaded_data = schema.load(transformed_data)
        return MappingProxyType(loaded_data)  # type: ignore[reportAssignmentType]

    def from_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data from the comicbox schema to this schema."""
        schema = self._schema
        transformed_data = glom(dict(data), dict(self.SPECS_FROM), glom_debug=True)
        self._swap_data_key(schema, transformed_data)
        loaded_data = schema.load(transformed_data)
        return MappingProxyType(loaded_data)  # type: ignore[reportAssignmentType]
