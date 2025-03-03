"""Metadata class for a comic archive."""

from collections.abc import Mapping
from copy import deepcopy
from logging import DEBUG, getLogger
from os import environ
from pprint import pformat
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_mixin import (
    NAME_KEY,
    ROLES_KEY,
    SERIES_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema

LOG = getLogger(__name__)


ORDERED_SET_KEYS = frozenset({"remainders"})

LOG = getLogger(__name__)


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    TRANSFORM_MAP = frozenbidict()
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType({})
    SIMPLE_STRING_SCHEMAS = MappingProxyType(
        {SERIES_KEY: NAME_KEY, VOLUME_KEY: VOLUME_NUMBER_KEY}
    )
    LIST_KEYS = frozenset()
    ROLE_SPELLING = MappingProxyType({"penciler": "Penciller"})

    def __init__(self, path=None):
        """Initialize instances."""
        self._path = path
        self._schema = self.SCHEMA_CLASS(path=path)

    ##################
    # UNRAP and WRAP #
    ##################

    def unwrap(self, data, wrap_tags=None) -> dict:
        """Unwrap the data from root tags."""
        result = data
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        try:
            for tag in wrap_tags:
                result = result[tag]
        except KeyError:
            pass
        return result

    def wrap(self, sub_data, wrap_tags=None, **_kwargs) -> dict:
        """Wrap the data in root tags."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        data = sub_data
        for tag in reversed(wrap_tags):
            data = {tag: data}

        return data

    def insert_sub_data(self, data, sub_data, wrap_tags=None):
        """Insert sub data into loaded data."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        if not wrap_tags:
            return data
        sub_root = data
        for tag in wrap_tags[:-1]:
            sub_root = sub_root[tag]
        sub_root = dict(sub_root)
        sub_root[wrap_tags[-1]] = sub_data
        return data

    ##############
    # TRANSFORMS #
    ##############

    def copy_keys(
        self,
        data: dict,
        transform_map: frozenbidict,
        to_comicbox: bool = False,  # noqa: FBT002
    ):
        """Copy values between schemas with transformed keys."""
        if to_comicbox:
            transform_map = transform_map.inverse
        for from_key, to_key in transform_map.items():
            value = data.pop(from_key, None)
            if value not in EMPTY_VALUES:
                data[to_key] = value
        return data

    def copy_keys_to(self, data: dict):
        """Copy keys to comicbox keys."""
        return self.copy_keys(data, self.TRANSFORM_MAP, to_comicbox=False)

    def copy_keys_from(self, data: dict):
        """Copy keys from comicbox keys."""
        return self.copy_keys(data, self.TRANSFORM_MAP, to_comicbox=True)

    def string_list_to_dicts_one(self, data, from_key, to_key):
        """Transform one sequence of strings to comicbox name objects."""
        names = data.pop(from_key, None)
        if names and (obj := {name: {} for name in names if name}):
            data[to_key] = obj

    def string_lists_to_dicts(self, data: dict):
        """Copy string lists to named objects in comicbox."""
        for from_key, to_key in self.STRINGS_TO_NAMED_OBJS_MAP.items():
            self.string_list_to_dicts_one(data, from_key, to_key)
        return data

    def name_dicts_to_string_lists(self, data: dict):
        """Copy named objects in comicbox to string lists."""
        for to_key, from_key in self.STRINGS_TO_NAMED_OBJS_MAP.items():
            obj = data.pop(from_key, {})
            if string_list := [name for name in obj if name]:
                if to_key not in self.LIST_KEYS:
                    string_list = set(string_list)
                data[to_key] = string_list
        return data

    def expand_str_to_schema(self, data):
        """Expand simple strings into schema structures."""
        for key, subkey in self.SIMPLE_STRING_SCHEMAS.items():
            value = data.get(key)
            if value is None or isinstance(value, Mapping):
                continue
            data[key] = {subkey: value}
        return data

    @classmethod
    def add_credit_role_to_comicbox_credits(
        cls, person_name: str, role_name: str, comicbox_credits: dict
    ):
        """Add a credit role to the comicbox credits."""
        if not (person_name and role_name):
            return
        if person_name not in comicbox_credits:
            comicbox_credits[person_name] = {ROLES_KEY: {}}
        role_name = cls.ROLE_SPELLING.get(role_name.lower(), role_name)
        comicbox_credits[person_name][ROLES_KEY][role_name] = {}

    TO_COMICBOX_PRE_TRANSFORM = (copy_keys_to, string_lists_to_dicts)
    TO_COMICBOX_POST_TRANSFORM = (expand_str_to_schema,)
    FROM_COMICBOX_PRE_TRANSFORM = (copy_keys_from, name_dicts_to_string_lists)
    FROM_COMICBOX_POST_TRANSFORM = ()

    ##################################
    # TRANSFORM TO AND FROM COMICBOX #
    ##################################

    def _run_transforms(  # noqa: PLR0913
        self, data, methods, unwrap_wrap_tags, wrap_wrap_tags, insert: bool, stamp: bool
    ):
        """
        Run transform methods.

        Transform methods operate on the sub schema, so this method unwraps and re-wraps them.
        """
        if not methods:
            return data
        debug_transform = environ.get("DEBUG_TRANSFORM", False)
        sub_data = self.unwrap(data, wrap_tags=unwrap_wrap_tags)
        if debug_transform and LOG.isEnabledFor(DEBUG):
            LOG.debug(f"{type(self)} sub_data:")
            LOG.debug(pformat(sub_data))
        for method in methods:
            # Get the overridden method from this isnstance, not the parents.
            sub_data = method(self, sub_data)
            if debug_transform and LOG.isEnabledFor(DEBUG):
                LOG.debug(f"{type(self)}.{method}:")
                LOG.debug(pformat(sub_data))
        if insert:
            data = self.insert_sub_data(data, sub_data, wrap_tags=wrap_wrap_tags)
        else:
            data = self.wrap(sub_data, wrap_tags=wrap_wrap_tags, stamp=stamp)
        return data

    def _transform_load(self, schema, data):
        """Load into new schema."""
        loaded_data = schema.load(data)
        if not isinstance(loaded_data, Mapping):
            reason = f"Loaded schema data is not a Mapping: {type(loaded_data)}"
            raise TypeError(reason)
        return loaded_data

    def to_comicbox(self, data) -> MappingProxyType:
        """Transform the data to a normalized comicbox schema."""
        data = deepcopy(dict(data))
        data = self._run_transforms(
            data,
            self.TO_COMICBOX_PRE_TRANSFORM,
            None,
            ComicboxYamlSchema.WRAP_TAGS,
            insert=False,
            stamp=False,
        )
        data = self._transform_load(ComicboxYamlSchema(path=self._path), data)
        data = self._run_transforms(
            data,
            self.TO_COMICBOX_POST_TRANSFORM,
            ComicboxYamlSchema.WRAP_TAGS,
            ComicboxYamlSchema.WRAP_TAGS,
            insert=True,
            stamp=False,
        )
        return MappingProxyType(data)

    def from_comicbox(self, data: Mapping, **_kwargs) -> MappingProxyType:
        """Transform the data from the comicbox schema to this schema."""
        data = deepcopy(dict(data))
        data = self._run_transforms(
            data,
            self.FROM_COMICBOX_PRE_TRANSFORM,
            ComicboxYamlSchema.WRAP_TAGS,
            None,
            insert=False,
            stamp=True,
        )
        data = self._transform_load(self._schema, data)
        data = self._run_transforms(
            data,
            self.FROM_COMICBOX_POST_TRANSFORM,
            None,
            None,
            insert=True,
            stamp=False,
        )
        return MappingProxyType(data)
