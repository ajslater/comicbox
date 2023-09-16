"""Metadata class for a comic archive."""
from copy import deepcopy
from types import MappingProxyType

from marshmallow import post_dump, pre_load

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.decorators import trap_error


class HierarchicalSchema(BaseSchema):
    """The Comicbox schema."""

    ROOT_TAG = "base"
    ROOT_TAGS = MappingProxyType({ROOT_TAG: {}})
    FILENAME = "base.txt"

    @trap_error(pre_load(pass_many=True))
    def strip_root_tags(self, data, **_kwargs):
        """Strip root tags.

        many=True unused but sets order before @pre_loads.
        """
        if sub_data := data.get(self.ROOT_TAG):
            data = sub_data
        return data

    @post_dump(pass_many=True)
    def wrap_in_root_tags(self, data, **_kwargs):
        """Wrap in root tags.

        many=True unused but sets order after all @post_dumps.
        """
        data_dict = deepcopy(dict(self.ROOT_TAGS))
        data_dict[self.ROOT_TAG].update(data)
        return data_dict
