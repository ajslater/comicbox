"""Comicbox Identifier Schemas."""

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import DictField
from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSubSchema


class IdentifierSchema(BaseSubSchema):  # Comet, CIX, CT, Metron
    """Identifier schema."""

    key = StringField()
    url = StringField()


class IdentifiedSchema(BaseSubSchema):  # Metron ONLY
    """Identified Schema."""

    identifiers = DictField(values=Nested(IdentifierSchema))


class IdentifiedNameSchema(IdentifiedSchema):  # Comicbox
    """Named Element with an identifier."""

    name = StringField()


class IdentifierPrimarySource(BaseSubSchema):
    """Identifiers Primary Source."""

    source = StringField(required=True)  # Metron ONLY
    url = StringField()  # Comicbox
