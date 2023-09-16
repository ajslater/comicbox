"""Comic yaml superclass."""
from decimal import Decimal
from sys import maxsize
from types import MappingProxyType
from typing import Union

from ruamel.yaml import YAML, StringIO

from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_base import ComicboxBaseSchema

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
        """Represent dict as a single line."""
        if isinstance(data, dict) and "index" in data:
            # data = dict(sorted(data.items()))
            return dumper.represent_mapping(_MAP_TAG, data, flow_style=True)

        return dumper.represent_dict(data)

    @classmethod
    def get_write_yaml(cls, dfs=False):
        """Get write yaml with special formatting."""
        yaml = YAML()
        yaml.default_flow_style = dfs
        if dfs:
            yaml.width = maxsize
        else:
            yaml.indent(mapping=2, sequence=4, offset=2)

        yaml.sort_base_mapping_type_on_output = True  # type: ignore
        yaml.representer.add_representer(Decimal, cls._decimal_representer)
        yaml.representer.add_representer(dict, cls._dict_flow_representer)
        return yaml

    @classmethod
    def dumps(cls, obj: dict, *args, dfs=False, **kwargs):
        """Dump dict to YAML string."""
        yaml = cls.get_write_yaml(dfs=dfs)
        with StringIO() as buf:
            yaml.dump(obj, buf, *args, **kwargs)
            return buf.getvalue()

    @staticmethod
    def loads(s: Union[bytes, str], *args, **kwargs):
        """Load YAML string into a dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            return YAML().load(cleaned_s, *args, **kwargs)
        return None


class ComicboxYamlSchema(ComicboxBaseSchema):
    """YAML schema customizations."""

    FILENAME = "comicbox.yaml"
    CONFIG_KEYS = frozenset({"yaml"})
    ROOT_TAG = "comicbox"
    ROOT_TAGS = MappingProxyType({ROOT_TAG: {}})

    class Meta(ComicboxBaseSchema.Meta):
        """Schema Options."""

        render_module = YamlRenderModule

    def dumps(self, obj, *args, dfs=False, **kwargs):
        """Use dfs for render."""
        serialized = self.dump(obj, **kwargs)
        return self.opts.render_module.dumps(serialized, *args, dfs=dfs, **kwargs)
