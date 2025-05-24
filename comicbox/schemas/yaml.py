"""Comic yaml superclass."""

from decimal import Decimal
from enum import Enum
from sys import maxsize

from ruamel.yaml import YAML, StringIO
from typing_extensions import override

from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicbox import BOOKMARK_KEY, ID_KEY_KEY, PAGE_KEYS
from comicbox.schemas.comicinfo import IMAGE_ATTRIBUTE

_TAG_YAML = "tag:yaml.org,2002"
_FLOAT_TAG = f"{_TAG_YAML}:float"
_MAP_TAG = f"{_TAG_YAML}:map"
_FLOW_KEYS = frozenset({IMAGE_ATTRIBUTE, *PAGE_KEYS} - {BOOKMARK_KEY, ID_KEY_KEY})


class YamlRenderModule:
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def _decimal_representer(dumper, data):
        """Represent decimals as a naked 2 precision float."""
        return dumper.represent_scalar(_FLOAT_TAG, format(data, ".2f"))

    @staticmethod
    def _dict_flow_representer(dumper, data):
        """Represent page dict as a single line."""
        if _FLOW_KEYS & data.keys():
            return dumper.represent_mapping(_MAP_TAG, data, flow_style=True)

        return dumper.represent_dict(data)

    @staticmethod
    def _none_representer(dumper, data):
        return dumper.represent_none(data)

    @staticmethod
    def _enum_representer(dumper, data):
        """Represent enums as their value."""
        return dumper.represent_str(data.value)

    @classmethod
    def _config_yaml(cls, yaml: YAML):
        yaml.sort_base_mapping_type_on_output = True  # pyright: ignore[reportAttributeAccessIssue]
        yaml.representer.add_representer(Decimal, cls._decimal_representer)
        yaml.representer.add_representer(type(None), cls._none_representer)
        yaml.representer.add_representer(dict, cls._dict_flow_representer)
        yaml.representer.add_multi_representer(Enum, cls._enum_representer)

    @classmethod
    def _get_write_yaml_dfs(cls):
        """Get write yaml with special formatting in default flow style."""
        yaml = YAML()
        yaml.default_flow_style = True
        yaml.width = maxsize
        cls._config_yaml(yaml)
        return yaml

    @classmethod
    def _get_write_yaml(cls):
        """Get write yaml with special formatting."""
        yaml = YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        cls._config_yaml(yaml)

        return yaml

    @classmethod
    def dumps(cls, obj: dict, *args, dfs=False, **kwargs):
        """Dump dict to YAML string."""
        yaml = cls._get_write_yaml_dfs() if dfs else cls._get_write_yaml()
        with StringIO() as buf:
            yaml.dump(obj, buf, *args, **kwargs)
            return buf.getvalue()

    @staticmethod
    def loads(s: bytes | str, *args, **kwargs):
        """Load YAML string into a dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
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
        self,
        obj,
        *args,
        dfs: bool = False,
        dump: bool = True,
        **kwargs,
    ):
        """Use dfs for render."""
        if dump:
            serialized: dict = super().dump(obj, *args, **kwargs)  # pyright: ignore[reportAssignmentType]
        else:
            serialized = obj
        return self.opts.render_module.dumps(serialized, *args, dfs=dfs, **kwargs)
