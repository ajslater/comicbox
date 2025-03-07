"""Comic yaml superclass."""

from decimal import Decimal
from enum import Enum
from sys import maxsize

from ruamel.yaml import YAML, StringIO

from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicbox_mixin import INDEX_KEY, ROOT_TAG

_TAG_YAML = "tag:yaml.org,2002"
_FLOAT_TAG = f"{_TAG_YAML}:float"
_MAP_TAG = f"{_TAG_YAML}:map"


class YamlRenderModule:
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def _decimal_representer(dumper, data):
        """Represent decimals as a naked 2 precision float."""
        return dumper.represent_scalar(_FLOAT_TAG, format(data, ".2f"))

    @staticmethod
    def _dict_flow_representer(dumper, data):
        """Represent page dict as a single line."""
        if INDEX_KEY in data:
            data = dict(sorted(data.items()))
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
    def get_write_yaml(cls, dfs: bool = False):  # noqa: FBT002
        """Get write yaml with special formatting."""
        yaml = YAML()
        yaml.default_flow_style = dfs
        if dfs:
            yaml.width = maxsize
        else:
            yaml.indent(mapping=2, sequence=4, offset=2)

        yaml.sort_base_mapping_type_on_output = True  # type: ignore[reportAssignmentType]
        yaml.representer.add_representer(Decimal, cls._decimal_representer)
        yaml.representer.add_representer(type(None), cls._none_representer)
        yaml.representer.add_representer(dict, cls._dict_flow_representer)
        yaml.representer.add_multi_representer(Enum, cls._enum_representer)
        return yaml

    @classmethod
    def dumps(cls, obj: dict, *args, dfs=False, **kwargs):
        """Dump dict to YAML string."""
        yaml = cls.get_write_yaml(dfs=dfs)
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

    def dump(self, obj, *args, allowed_null_keys=None, **kwargs):
        """Allow null keys on dump."""
        saved_null_keys = set()
        if allowed_null_keys:
            sub_data = obj.get(ROOT_TAG, {})
            for key in allowed_null_keys:
                if key in sub_data and sub_data.get(key) is None:
                    saved_null_keys.add(key)
        serialized: dict = super().dump(obj, *args, **kwargs)  # type: ignore[reportAssignmentType]
        if saved_null_keys:
            if ROOT_TAG not in serialized:
                serialized[ROOT_TAG] = {}
            for key in saved_null_keys:
                serialized[ROOT_TAG][key] = None
        return serialized

    def dumps(self, obj, *args, dfs=False, allowed_null_keys=None, **kwargs):
        """Use dfs for render."""
        serialized: dict = self.dump(obj, allowed_null_keys=allowed_null_keys, **kwargs)  # type: ignore[reportAssignmentType]
        return self.opts.render_module.dumps(serialized, *args, dfs=dfs, **kwargs)
