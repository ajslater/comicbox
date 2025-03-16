"""Metadata class for a comic archive."""

from collections.abc import Mapping
from copy import deepcopy
from logging import DEBUG, getLogger
from os import environ
from pprint import pformat
from types import MappingProxyType

from bidict import frozenbidict
from glom import Assign, glom

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_mixin import ROLES_KEY
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.transform_map import transform_map

LOG = getLogger(__name__)


def string_list_to_name_obj(names):
    """Transform one sequence of strings to comicbox name objects."""
    return {name: {} for name in names if name}


def name_obj_to_string_list(obj):
    """Transform one comicbox name object to a string list."""
    return [name for name in obj if name]


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    TRANSFORM_MAP = frozenbidict()
    ROLE_SPELLING = MappingProxyType({"penciler": "Penciller"})

    def __init__(self, path=None):
        """Initialize instances."""
        self._path = path
        self._schema = self.SCHEMA_CLASS(path=path)

    ##################
    # UNRAP and WRAP #
    ##################

    def unwrap(self, data, wrap_tags="") -> dict:
        """Unwrap the data from root tags."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        return glom(data, wrap_tags, default=None)

    def wrap(self, sub_data, wrap_tags="", **_kwargs) -> dict:
        """Wrap the data in root tags."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        assign = Assign(wrap_tags, sub_data, missing=dict)
        return glom({}, assign)

    def insert_sub_data(self, data, sub_data, wrap_tags=""):
        """Insert sub data into loaded data."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        if not wrap_tags:
            return data
        assign = Assign(wrap_tags, sub_data, missing=dict)
        return glom(data, assign)

    ##############
    # TRANSFORMS #
    ##############

    def transform_keys_to(self, data: dict):
        """Copy keys to comicbox keys."""
        return transform_map(self.TRANSFORM_MAP, data, in_place=True)

    def transform_keys_from(self, data: dict):
        """Copy keys from comicbox keys."""
        return transform_map(self.TRANSFORM_MAP.inverse, data, in_place=True)

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

    TO_COMICBOX_PRE_TRANSFORM = (transform_keys_to,)
    TO_COMICBOX_POST_TRANSFORM = ()
    FROM_COMICBOX_PRE_TRANSFORM = (transform_keys_from,)
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
