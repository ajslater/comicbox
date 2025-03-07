"""Metadata class for a comic archive."""

from collections.abc import Mapping
from copy import deepcopy
from logging import DEBUG, getLogger
from os import environ
from pprint import pformat
from types import MappingProxyType

from bidict import bidict

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_mixin import (
    CONTRIBUTORS_KEY,
    SERIES_KEY,
    SERIES_NAME_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.comicbox_mixin import ComicboxTransformMixin

LOG = getLogger(__name__)


ORDERED_SET_KEYS = frozenset({"remainders"})

LOG = getLogger(__name__)


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    TRANSFORM_MAP = bidict()
    CONTRIBUTOR_COMICBOX_MAP = MappingProxyType({})
    CONTRIBUTOR_SCHEMA_MAP = MappingProxyType({})
    SIMPLE_STRING_SCHEMAS = MappingProxyType(
        {SERIES_KEY: SERIES_NAME_KEY, VOLUME_KEY: VOLUME_NUMBER_KEY}
    )

    def __init__(self, path=None):
        """Initialize instances."""
        self._path = path
        self._schema = self.SCHEMA_CLASS(path=path)

    ##################
    # UNRAP and WRAP #
    ##################

    def unwrap(self, data, root_tags=None) -> dict:
        """Unwrap the data from root tags."""
        result = data
        if not root_tags:
            root_tags = self.SCHEMA_CLASS.ROOT_TAGS
        try:
            for tag in root_tags:
                result = result[tag]
        except KeyError:
            pass
        return result

    def wrap(self, sub_data, root_tags=None, **_kwargs) -> dict:
        """Wrap the data in root tags."""
        if not root_tags:
            root_tags = self.SCHEMA_CLASS.ROOT_TAGS
        data = sub_data
        for tag in reversed(root_tags):
            data = {tag: data}

        return data

    def insert_sub_data(self, data, sub_data, root_tags=None):
        """Insert sub data into loaded data."""
        if not root_tags:
            root_tags = self.SCHEMA_CLASS.ROOT_TAGS
        sub_root = data
        for tag in root_tags[:-1]:
            sub_root = sub_root[tag]
        sub_root = dict(sub_root)
        sub_root[root_tags[-1]] = sub_data
        return data

    ##############
    # TRANSFORMS #
    ##############

    def copy_keys(self, data, transform_map, to_comicbox: bool = False):  # noqa: FBT002
        """Copy values between schemas with transformed keys."""
        if to_comicbox:
            transform_map = transform_map.inverse
        for from_key, to_key in transform_map.items():
            value = data.pop(from_key, None)
            if value not in EMPTY_VALUES:
                data[to_key] = value
        return data

    def copy_keys_to(self, data):
        """Copy keys to comicbox keys."""
        return self.copy_keys(data, self.TRANSFORM_MAP, to_comicbox=False)

    def copy_keys_from(self, data):
        """Copy keys from comicbox keys."""
        return self.copy_keys(data, self.TRANSFORM_MAP, to_comicbox=True)

    def canonize_contributors(self, data):
        """Force contributors into comicbox canon roles."""
        contributors = data.get(CONTRIBUTORS_KEY)
        if not contributors:
            return data
        for role, persons in contributors.items():
            canon_role = ComicboxTransformMixin.CONTRIBUTOR_COMICBOX_MAP.get(role)
            if canon_role == role:
                continue

            del data[CONTRIBUTORS_KEY][role]
            if not canon_role:
                continue
            data[CONTRIBUTORS_KEY][canon_role] = persons
        return data

    def expand_str_to_schema(self, data):
        """Expand simple strings into schema structures."""
        for key, subkey in self.SIMPLE_STRING_SCHEMAS.items():
            value = data.get(key)
            if value is None or isinstance(value, Mapping):
                continue
            data[key] = {subkey: value}
        return data

    TO_COMICBOX_PRE_TRANSFORM = (copy_keys_to,)
    TO_COMICBOX_POST_TRANSFORM = (canonize_contributors, expand_str_to_schema)
    FROM_COMICBOX_PRE_TRANSFORM = (copy_keys_from,)
    FROM_COMICBOX_POST_TRANSFORM = ()

    ##################################
    # TRANSFORM TO AND FROM COMICBOX #
    ##################################

    def _run_transforms(  # noqa: PLR0913
        self, data, methods, unwrap_root_tags, wrap_root_tags, insert: bool, stamp: bool
    ):
        """
        Run transform methods.

        Transform methods operate on the sub schema, so this method unwraps and re-wraps them.
        """
        if not methods:
            return data
        debug_transform = environ.get("DEBUG_TRANSFORM", False)
        sub_data = self.unwrap(data, root_tags=unwrap_root_tags)
        if debug_transform and LOG.isEnabledFor(DEBUG):
            LOG.debug(f"{type(self)} sub_data:")
            LOG.debug(pformat(sub_data))
        for method in methods:
            sub_data = method(self, sub_data)
            if debug_transform and LOG.isEnabledFor(DEBUG):
                LOG.debug(f"{type(self)}.{method}:")
                LOG.debug(pformat(sub_data))
        if insert:
            data = self.insert_sub_data(data, sub_data, root_tags=wrap_root_tags)
        else:
            data = self.wrap(sub_data, root_tags=wrap_root_tags, stamp=stamp)
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
            ComicboxYamlSchema.ROOT_TAGS,
            insert=False,
            stamp=False,
        )
        data = self._transform_load(ComicboxYamlSchema(path=self._path), data)
        data = self._run_transforms(
            data,
            self.TO_COMICBOX_POST_TRANSFORM,
            ComicboxYamlSchema.ROOT_TAGS,
            ComicboxYamlSchema.ROOT_TAGS,
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
            ComicboxYamlSchema.ROOT_TAGS,
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
