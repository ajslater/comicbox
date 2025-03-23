"""Transform to and from a format and comicbox format."""

from collections.abc import Mapping
from logging import getLogger
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.transform_map import KeyTransforms, transform_map

LOG = getLogger(__name__)


def string_list_to_name_obj(_source_data: Mapping, names):
    """Transform one sequence of strings to comicbox name objects."""
    return {name: {} for name in names if name}


def name_obj_to_string_list(_source_data: Mapping, obj):
    """Transform one comicbox name object to a string list."""
    return [name for name in obj if name]


def name_obj_to_string_list_key_transforms(key_map):
    """Create a name obj to string list key transform spec for a key map."""
    return KeyTransforms(
        key_map=key_map,
        to_cb=string_list_to_name_obj,
        from_cb=name_obj_to_string_list,
    )


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    TRANSFORM_MAP = frozenbidict()

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

    def _transform(
        self,
        spec_map: Mapping,
        schema: BaseSchema,
        data: Mapping,
        swap_data_key: bool,
    ) -> MappingProxyType:
        """Transform formats to and from normalized Comicbox schema."""
        transformed_data = transform_map(spec_map, data)
        self._swap_data_key(swap_data_key, schema, transformed_data)
        loaded_data = schema.load(transformed_data)
        return MappingProxyType(loaded_data)  # type: ignore[reportAssignmentType]

    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data to a normalized comicbox schema."""
        schema = ComicboxYamlSchema(path=self._path)
        return self._transform(self.TRANSFORM_MAP, schema, data, swap_data_key=False)

    def from_comicbox(self, data: Mapping) -> MappingProxyType:
        """Transform the data from the comicbox schema to this schema."""
        schema = self._schema
        return self._transform(
            self.TRANSFORM_MAP.inverse,
            schema,
            data,
            swap_data_key=True,
        )
