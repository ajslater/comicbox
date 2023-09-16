"""Marshmallow pycountry fields."""
from logging import getLogger

from marshmallow import fields
from pycountry import pycountry

from comicbox.fields.fields import DeserializeMeta, StringField

LOG = getLogger(__name__)


class PyCountryField(fields.String, metaclass=DeserializeMeta):
    """A pycountry value."""

    @staticmethod
    def _clean_name(name):
        if not name:
            return None
        name = StringField().deserialize(name)
        if not name:
            return None
        return name.strip()

    @classmethod
    def _get_pycountry(cls, tag, name):
        """Get pycountry object for a country or language tag."""
        try:
            name = cls._clean_name(name)
            if not name:
                return None

            lower_tag = tag.lower()
            if lower_tag.startswith("lang"):
                module = pycountry.languages
            elif lower_tag.startswith("country"):
                module = pycountry.countries
            else:
                LOG.warning(f"no pycountry module for {tag}")
                module = None
            if module:
                if len(name) == 2:  # noqa PLR2004
                    # Language lookup fails for 'en' unless alpha_2 is specified.
                    obj = module.get(alpha_2=name)
                else:
                    obj = module.lookup(name)
            else:
                obj = None
        except Exception as exc:
            LOG.warning(exc)
            obj = None

        if obj is None:
            LOG.warning(f"Couldn't find {tag} for {name}")

        return obj

    def _deserialize(self, value, attr, _data, **_kwargs):
        """Return the alpha 2 encoding."""
        pc_obj = self._get_pycountry(attr, value)
        if pc_obj:
            return pc_obj.alpha_2
        return None

    def _serialize(self, value, attr, _obj, **_kwargs):
        """Return the long name."""
        pc_obj = self._get_pycountry(attr, value)
        if pc_obj:
            return pc_obj.name
        return None
