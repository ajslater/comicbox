"""XML Metadata parser superclass."""
from abc import ABC
from copy import deepcopy
from logging import getLogger
from types import MappingProxyType
from typing import Union

import xmltodict
from marshmallow.decorators import post_dump, pre_load
from stringcase import pascalcase

from comicbox.fields.collections import (
    IdentifiersField,
    StringListField,
    StringSetField,
)
from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    PAGES_KEY,
    ComicboxBaseSchema,
)
from comicbox.schemas.contributors import ContributorsSchema
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.page_info import PageInfoSchema

LOG = getLogger(__name__)


class XmlRenderModule:
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to XML string."""
        return xmltodict.unparse(
            obj, *args, pretty=True, short_empty_elements=True, **kwargs
        )

    @staticmethod
    def loads(s: Union[bytes, str], *args, **kwargs):
        """Load XML string into a dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            return xmltodict.parse(cleaned_s, *args, **kwargs)
        return None


def get_pascal_case_key_map(schema_class, attr=False):
    """Create an xml key map with pascal cased keys and attributes."""
    keys = schema_class().fields
    key_map = {}
    for key in keys:
        tag = "@" if attr else ""
        tag += pascalcase(key)
        key_map[tag] = key
    return MappingProxyType(key_map)


class ComicboxXmlSchema(ComicboxBaseSchema, ABC):
    """XML Schema customizations."""

    CONFIG_KEYS = frozenset({"xml"})
    CREDIT_KEY_MAP = MappingProxyType({})
    FILENAME = "comicbox.xml"
    ROOT_TAG = "Comicbox"
    ROOT_TAGS = MappingProxyType(
        {
            ROOT_TAG: {
                "@xmlns:comicbox": "https://github.com/ajslater/comicbox/",
                "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "@xsi:schemaLocation": "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.xsd",
            }
        }
    )
    DATA_KEY_MAP = get_pascal_case_key_map(ComicboxBaseSchema)
    CONTRIBUTORS_KEY_MAP = get_pascal_case_key_map(ContributorsSchema)
    PAGE_INFO_KEY_MAP = get_pascal_case_key_map(PageInfoSchema, True)
    _SEQUENCE_OK_FIELDS = (IdentifiersField, StringListField, StringSetField)
    _PAGES_TAG = "Pages"
    _PAGE_TAG = "Page"

    def _map_nested_schema_data_keys(self, field_name, inner=False, key_map=None):
        """Map nested schema keys to pascal case tags."""
        field = self.fields.get(field_name)
        if not field:
            return
        schema = field.inner.schema if inner else field.schema  # type: ignore
        schema.set_path(self._path)
        self.map_data_keys(key_map, schema)

    def __init__(self, *args, **kwargs):
        """Add data_keys to PagesInfo."""
        super().__init__(*args, **kwargs)
        self._map_nested_schema_data_keys(
            CONTRIBUTORS_KEY, key_map=self.CONTRIBUTORS_KEY_MAP
        )
        self._map_nested_schema_data_keys(
            PAGES_KEY, inner=True, key_map=self.PAGE_INFO_KEY_MAP
        )

    @trap_error(pre_load)
    def first_if_sequence(self, data, **_kwargs):
        """If a collection is submitted for a single value, take the first value.

        Mostly useful when xmltodict parses multiple values into lists.
        """
        data_changes = {}
        for data_key, value in data.items():
            try:
                key = self.DATA_KEY_MAP.get(data_key)
                if not key:
                    continue
                field = self.fields.get(key)
                if not field:
                    continue
                if not isinstance(field, self._SEQUENCE_OK_FIELDS):
                    new_value = value
                    if isinstance(new_value, (set, frozenset)):
                        new_value = list(value)
                    if isinstance(new_value, (list, tuple)):
                        new_value = new_value[0]
                        data_changes[data_key] = new_value
            except Exception:
                LOG.exception(
                    f"{self._path} Getting first of sequence for tag {data_key}"
                )
                data_changes[data_key] = None
        if data_changes:
            data = deepcopy(dict(data))
            data.update(data_changes)
        return data

    @trap_error(pre_load)
    def hoist_page_info(self, data, **_kwargs):
        """Hoist Page list directly under pages."""
        if not data:
            return data
        pages_holder = data.get(self._PAGES_TAG)
        if not pages_holder:
            return data
        if pages := pages_holder.get(self._PAGE_TAG):
            data = deepcopy(dict(data))
            data[self._PAGES_TAG] = pages
        return data

    @post_dump
    def lower_page_info(self, data, **_kwargs):
        """Lower pages list down into a Page key."""
        if pages := data.get(self._PAGES_TAG):
            data = deepcopy(dict(data))
            data[self._PAGES_TAG] = {self._PAGE_TAG: pages}
        return data

    class Meta(ComicboxBaseSchema.Meta):
        """Schema Options."""

        render_module = XmlRenderModule
