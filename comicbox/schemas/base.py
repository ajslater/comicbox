"""Skip keys instead of throwing errors."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime
    import decimal
    import pathlib

    import ruamel.yaml

    import comicbox.fields.comicinfo
    import comicbox.fields.enum_fields
    import comicbox.schemas.comicbox.publishing
    import comicbox.schemas.comictagger
    import comicbox.schemas.pdf

from abc import ABC
from pathlib import Path
from types import MappingProxyType

from loguru import logger
from marshmallow import EXCLUDE
from marshmallow.decorators import (
    post_dump,
    post_load,
    pre_dump,
    pre_load,
)
from marshmallow.types import RenderModule, StrSequenceOrSet
from typing_extensions import override

from comicbox.empty import is_empty
from comicbox.fields.fields import StringField
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.error_store import ClearingErrorStoreSchema


class BaseRenderModule(RenderModule, ABC):
    """Base Render Module."""

    @staticmethod
    def clean_string(s: str | bytes | bytearray) -> str | None:
        """Clean a string."""
        return StringField(clean_tabs=True).deserialize(s)


class BaseSubSchema(ClearingErrorStoreSchema, ABC):
    """Base schema."""

    TAG_ORDER: tuple[str, ...] = ()
    # Currently only mapping "pages" and "reprints" fields for each schema for Codex out of laziness
    # But this should speed up Codex reads
    DELETE_KEY_MAP = MappingProxyType({})

    def _create_exclude(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", exclude: StrSequenceOrSet) -> set[str]:
        final_exclude = set()
        fields = getattr(self, "fields", {})
        for key in exclude:
            if "." in key:
                # Deep keypaths not allowed
                continue
            if local_keys := self.DELETE_KEY_MAP.get(key):
                final_exclude |= local_keys
            elif key in fields:
                final_exclude.add(key)
        return final_exclude

    def __init__(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", *args: None, exclude: StrSequenceOrSet = (), **kwargs: "bool|list[Any]|pathlib.PosixPath|str|None") -> None:
        """Initialize with exclude keys."""
        exclude = self._create_exclude(exclude)
        super().__init__(*args, exclude=exclude, **kwargs)

    @classmethod
    def pre_load_validate(cls: "type[comicbox.schemas.comicbox.publishing.BaseSubSchema|Any]", data: "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[dict[str, dict[str, str]]]]|dict[str, list[str]]|dict[str, str]|ruamel.yaml.CommentedMap") -> "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, dict[str, dict[str, dict[Any, Any]]]]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[int]]|dict[str, str]|ruamel.yaml.CommentedMap":
        """Validate schema type first thing to fail as early as possible."""
        # Meant to be overridden in BaseSchema
        return data

    @trap_error(pre_load)
    def pre_load(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", data: "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, decimal.Decimal]]]|dict[str, dict[str, dict[str, dict[str, int]]]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, list[dict[str, str]]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[dict[str, str]]]|dict[str, str]|ruamel.yaml.CommentedMap|MappingProxyType[str, dict[str, dict[str, str]]]|None", **_kwargs: bool|str) -> "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, dict[Any, Any]]]]|dict[str, dict[str, dict[str, int]]]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, list[str]]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[dict[str, str]]]|dict[str, str]|dict[Any, Any]|ruamel.yaml.CommentedMap|MappingProxyType[str, dict[str, dict[str, list[dict[str, str]]]]]|MappingProxyType[str, dict[str, int]]":
        """Singular pre_load hook."""
        return self.pre_load_validate(data)

    @classmethod
    def clean_empties(cls: "type[comicbox.schemas.comicbox.publishing.BaseSubSchema|Any]", data: dict) -> dict:
        """Clean empties from loaded data."""
        return {k: v for k, v in data.items() if not is_empty(v)}

    @trap_error(post_load)
    def post_load(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", data: dict[str|Any, int|list[Any]|str|Any], **_kwargs: bool|str) -> "dict[str|Any, comicbox.fields.enum_fields.ComicInfoPageTypeEnum|int|str|Any]":
        """Singular post_load hook."""
        return self.clean_empties(data)

    @pre_dump
    def pre_dump(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema", data: "dict[str, dict[str, datetime.datetime]]|dict[str, dict[str, dict[str, decimal.Decimal]]]|dict[str, str]|MappingProxyType[str, dict[str, comicbox.fields.enum_fields.ReadingDirectionEnum]]|MappingProxyType[str, dict[str, dict[str, dict[str, set[str]]]]]|MappingProxyType[str, dict[str, dict[str, dict[str, str]]]]|MappingProxyType[str, dict[str, dict[str, int]]]|MappingProxyType[str, dict[str, dict[str, list[dict[str, str]]]]]|MappingProxyType[str, dict[str, dict[str, str]]]|MappingProxyType[str, dict[str, int]]|MappingProxyType[str, dict[str, set[str]]]|MappingProxyType[str, dict[str, str]]", **_kwargs: bool) -> "dict[str, dict[str, dict[str, decimal.Decimal]]]|dict[str, dict[str, str]]|dict[str, str]|MappingProxyType[str, dict[str, datetime.date]]|MappingProxyType[str, dict[str, datetime.datetime]]|MappingProxyType[str, dict[str, dict[str, dict[str, datetime.datetime]]]]|MappingProxyType[str, dict[str, dict[str, dict[str, str]]]]|MappingProxyType[str, dict[str, dict[str, int]]]|MappingProxyType[str, dict[str, dict[str, str]]]|MappingProxyType[str, dict[str, int]]|MappingProxyType[str, dict[str, list[str]]]|MappingProxyType[str, dict[str, set[str]]]|MappingProxyType[str, dict[str, str]]":
        """Singular pre_dump hook."""
        return data

    @classmethod
    def _sort_tag_by_order(cls: "type[comicbox.schemas.pdf.JsonSchema|Any]", data: dict) -> dict:
        """Sort tag by schema class order tuple."""
        result = {}
        for tag in cls.TAG_ORDER:
            value = data.get(tag)
            if is_empty(value):
                continue
            result[tag] = value
        return result

    @classmethod
    def sort_dump(cls: "type[comicbox.schemas.comicbox.publishing.BaseSubSchema|Any]", data: dict) -> dict:
        """Sort dump by key."""
        if cls.TAG_ORDER:
            data = cls._sort_tag_by_order(data)
        else:
            data = {k: v for k, v in sorted(data.items()) if not is_empty(v)}
        return data

    @post_dump
    def post_dump(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema|Any", data: dict, **_kwargs: bool) -> dict:
        """Singular post_dump hook."""
        return self.sort_dump(data)

    def loadf(self, path) -> list | None | dict:
        """Read the string from the designated file."""
        with Path(path).open("r") as f:
            str_data = f.read()
        return self.loads(str_data)

    def dumpf(self: "comicbox.schemas.comicbox.publishing.BaseSubSchema", data: "MappingProxyType[str, datetime.datetime|dict[str, dict[str, int]]|dict[str, dict[str, list[dict[str, str]]]]|dict[str, dict[str, str]]|dict[str, set[str]]|dict[str, str]]", path: "pathlib.PosixPath", **kwargs: None) -> None:
        """Write the string in the designated file."""
        str_data = self.dumps(data, **kwargs) + "\n"
        with Path(path).open("w") as f:
            f.write(str_data)

    class Meta(ClearingErrorStoreSchema.Meta):
        """Schema options."""

        unknown = EXCLUDE


class BaseSchema(BaseSubSchema, ABC):
    """Top level base schema that traps errors and records path."""

    ROOT_TAG: str = ""
    ROOT_DATA_KEY: str = ""
    ROOT_KEYPATH: str = ""
    LEGACY_NESTED_MD_KEYPATH: str = ""
    HAS_PAGE_COUNT: bool = False
    HAS_PAGES: bool = False

    @override
    @classmethod
    def pre_load_validate(cls: "type[comicbox.schemas.comictagger.BaseSchema]", data: "dict[str, None]|dict[str, dict[str, None]]|dict[str, dict[str, comicbox.fields.comicinfo.ComicInfoAgeRatingEnum]]|dict[str, dict[str, dict[str, None]]]|dict[str, dict[str, dict[str, str]]]|dict[str, dict[str, int]]|dict[str, dict[str, list[str]]]|dict[str, dict[str, set[str]]]|dict[str, dict[str, str]]|dict[str, str]|ruamel.yaml.CommentedMap|MappingProxyType[str, dict[str, dict[str, str]]]|MappingProxyType[str, dict[str, str]]|None") -> dict:
        """Validate the root tag so we don't confuse it with other JSON."""
        if not data:
            reason = "No data."
            logger.debug(reason)
            data = {}
        elif cls.ROOT_TAG not in data and cls.ROOT_DATA_KEY not in data:
            reason = f"Root tag '{cls.ROOT_TAG}' not found in {tuple(data.keys())}."
            logger.debug(reason)
            # Do not throw an exception so the trapper doesn't trap it and the
            # loader tries another schema. Return empty dict.
            data = {}
        return data
