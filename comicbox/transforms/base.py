"""Metadata class for a comic archive."""

from collections.abc import Mapping
from copy import deepcopy
from logging import getLogger
from types import MappingProxyType

from bidict import frozenbidict
from glom import Assign, glom

from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_mixin import ROLES_KEY
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.transforms.transform_map import KeyTransforms, transform_map

LOG = getLogger(__name__)


def string_list_to_name_obj(names):
    """Transform one sequence of strings to comicbox name objects."""
    return {name: {} for name in names if name}


def name_obj_to_string_list(obj):
    """Transform one comicbox name object to a string list."""
    return [name for name in obj if name]


def name_obj_to_string_list_key_transforms(key_map):
    """Create a name obj to string list key transform spec for a key map."""
    return KeyTransforms(
        key_map=key_map,
        to_cb=string_list_to_name_obj,
        from_cb=name_obj_to_string_list,
    )


def add_credit_role_to_comicbox_credits(
    role_spelling: MappingProxyType,
    person_name: str,
    role_name: str,
    comicbox_credits: dict,
):
    """Add a credit role to the comicbox credits."""
    if not (person_name and role_name):
        return
    if person_name not in comicbox_credits:
        comicbox_credits[person_name] = {ROLES_KEY: {}}
    role_name = role_spelling.get(role_name.lower(), role_name)
    comicbox_credits[person_name][ROLES_KEY][role_name] = {}


class BaseTransform:
    """Base Transform methods."""

    SCHEMA_CLASS = BaseSchema
    TRANSFORM_MAP = frozenbidict()
    TOP_TAG_MAP = frozenbidict()
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
        top_tags = transform_map(self.TOP_TAG_MAP, data)
        sub_data = glom(data, wrap_tags, default=None)
        if top_tags and sub_data:
            sub_data.update(top_tags)
        return sub_data

    def wrap(self, sub_data, wrap_tags="", **_kwargs) -> dict:
        """Wrap the data in root tags."""
        if not wrap_tags:
            wrap_tags = self.SCHEMA_CLASS.WRAP_TAGS
        top_tags = transform_map(self.TOP_TAG_MAP.inverse, sub_data)
        data = glom({}, Assign(wrap_tags, sub_data, missing=dict))
        if top_tags and data:
            data.update(top_tags)
        return data

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
        if not self.TRANSFORM_MAP:
            return data
        return transform_map(self.TRANSFORM_MAP, data)

    def transform_keys_from(self, data: dict):
        """Copy keys from comicbox keys."""
        if not self.TRANSFORM_MAP:
            return data
        return transform_map(self.TRANSFORM_MAP.inverse, data)

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

    TO_COMICBOX_PRE_TRANSFORM = ()
    FROM_COMICBOX_PRE_TRANSFORM = ()

    ##################################
    # TRANSFORM TO AND FROM COMICBOX #
    ##################################

    def _run_transforms(  # noqa: PLR0913
        self,
        data,
        methods,
        unwrap_wrap_tags,
        wrap_wrap_tags,
        insert: bool,
        stamp: bool,
        final_method=None,
    ):
        """
        Run transform methods.

        Transform methods operate on the sub schema, so this method unwraps and re-wraps them.
        """
        if not methods and not final_method:
            return data
        sub_data = self.unwrap(data, wrap_tags=unwrap_wrap_tags)
        for method in methods:
            # Get the overridden method from this isnstance, not the parents.
            sub_data = method(self, sub_data)
        if final_method:
            sub_data = final_method(sub_data)
        if insert:
            data = self.insert_sub_data(data, sub_data, wrap_tags=wrap_wrap_tags)
        else:
            data = self.wrap(sub_data, wrap_tags=wrap_wrap_tags, stamp=stamp)
        return data

    def to_comicbox(self, in_data) -> MappingProxyType:
        """Transform the data to a normalized comicbox schema."""
        data = deepcopy(dict(in_data))
        data = self._run_transforms(
            data,
            self.TO_COMICBOX_PRE_TRANSFORM,
            None,
            ComicboxYamlSchema.WRAP_TAGS,
            insert=False,
            stamp=False,
            final_method=self.transform_keys_to,
        )
        data: dict = ComicboxYamlSchema(path=self._path).load(data)  # type: ignore[reportAssignmentType]
        return MappingProxyType(data)

    def from_comicbox(self, in_data: Mapping, **_kwargs) -> MappingProxyType:
        """Transform the data from the comicbox schema to this schema."""
        data = deepcopy(dict(in_data))
        data = self._run_transforms(
            data,
            self.FROM_COMICBOX_PRE_TRANSFORM,
            ComicboxYamlSchema.WRAP_TAGS,
            None,
            insert=False,
            stamp=True,
            final_method=self.transform_keys_from,
        )
        data: dict = self._schema.load(data)  # type: ignore[reportAssignmentType]
        return MappingProxyType(data)
