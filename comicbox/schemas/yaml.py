"""Comic yaml superclass."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime
    import types

    import ruamel.yaml

    import tests.schemas.test_yaml

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from sys import maxsize

from ruamel.yaml import YAML, StringIO
from typing_extensions import override

from comicbox.schemas.base import BaseRenderModule, BaseSchema, BaseSubSchema
from comicbox.schemas.comicbox import BOOKMARK_KEY, ID_KEY_KEY, PAGE_KEYS
from comicbox.schemas.comicinfo import IMAGE_ATTRIBUTE

_TAG_YAML = "tag:yaml.org,2002"
_FLOAT_TAG = f"{_TAG_YAML}:float"
_MAP_TAG = f"{_TAG_YAML}:map"
_FLOW_KEYS = frozenset({IMAGE_ATTRIBUTE, *PAGE_KEYS} - {BOOKMARK_KEY, ID_KEY_KEY})


class YamlRenderModule(BaseRenderModule):
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def _decimal_representer(dumper: "ruamel.yaml.RoundTripRepresenter", data: Decimal) -> "ruamel.yaml.ScalarNode":
        """Represent decimals as a naked 2 precision float."""
        return dumper.represent_scalar(_FLOAT_TAG, format(data, ".2f"))

    @staticmethod
    def _dict_flow_representer(dumper: "ruamel.yaml.RoundTripRepresenter", data: "dict[str, dict[str, datetime.datetime|dict[str, dict[Any, Any]]|dict[str, str]|str]]") -> "ruamel.yaml.MappingNode":
        """Represent page dict as a single line."""
        if _FLOW_KEYS & data.keys():
            return dumper.represent_mapping(_MAP_TAG, data, flow_style=True)

        return dumper.represent_dict(data)

    @staticmethod
    def _none_representer(dumper: "ruamel.yaml.RoundTripRepresenter", data: None) -> "ruamel.yaml.ScalarNode":
        return dumper.represent_none(data)

    @staticmethod
    def _enum_representer(dumper: "ruamel.yaml.RoundTripRepresenter", data: Enum) -> "ruamel.yaml.ScalarNode":
        """Represent enums as their value."""
        return dumper.represent_str(data.value)

    @classmethod
    def _config_yaml(cls: "type[tests.schemas.test_yaml.YamlRenderModule]", yaml: YAML) -> None:
        yaml.sort_base_mapping_type_on_output = True  # pyright: ignore[reportAttributeAccessIssue]
        yaml.representer.add_representer(Decimal, cls._decimal_representer)
        yaml.representer.add_representer(type(None), cls._none_representer)
        yaml.representer.add_representer(dict, cls._dict_flow_representer)
        yaml.representer.add_multi_representer(Enum, cls._enum_representer)

    @classmethod
    def _get_write_yaml_dfs(cls: "type[tests.schemas.test_yaml.YamlRenderModule]") -> YAML:
        """Get write yaml with special formatting in default flow style."""
        yaml = YAML()
        yaml.default_flow_style = True
        yaml.width = maxsize
        return yaml

    @classmethod
    def _get_write_yaml(cls: "type[tests.schemas.test_yaml.YamlRenderModule]") -> YAML:
        """Get write yaml with special formatting."""
        yaml = YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        return yaml

    @override
    @classmethod
    def dumps(cls: "type[tests.schemas.test_yaml.YamlRenderModule]", obj: Mapping, *args: None, dfs: bool=False, **kwargs: None) -> str:
        """Dump dict to YAML string."""
        yaml = cls._get_write_yaml_dfs() if dfs else cls._get_write_yaml()
        cls._config_yaml(yaml)
        with StringIO() as buf:
            yaml.dump(dict(obj), buf, *args, **kwargs)
            return buf.getvalue()

    @override
    @classmethod
    def loads(cls: "type[tests.schemas.test_yaml.YamlRenderModule]", s: str | bytes | bytearray, *args: None, **kwargs: None) -> Any:
        """Load YAML string into a dict."""
        if cleaned_s := cls.clean_string(s):
            return YAML().load(cleaned_s, *args, **kwargs)
        return None


class YamlSubSchema(BaseSubSchema):
    """YAML sub schema."""


class YamlSchema(BaseSchema):
    """YAML schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = YamlRenderModule

    @override
    def dumps(
        self: Any,
        obj: "dict[str, dict[str, str]]|types.MappingProxyType[str, dict[str, dict[str, dict[str, int]]]]|types.MappingProxyType[str, dict[str, dict[str, int]]]|types.MappingProxyType[str, dict[str, dict[str, str]]]|types.MappingProxyType[str, dict[str, int]]|types.MappingProxyType[str, dict[str, str]]|Any",
        *args: None,
        dfs: bool = False,
        dump: bool = True,
        **kwargs: None,
    ) -> str:
        """Use dfs for render."""
        if dump:
            # Run hooks
            serialized: dict = self.dump(obj, *args, **kwargs)  # pyright: ignore[reportAssignmentType]
        else:
            serialized = obj
        return self.opts.render_module.dumps(serialized, *args, dfs=dfs, **kwargs)
