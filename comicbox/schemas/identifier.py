"""Identifiers Schema."""

from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSubSchema

NSS_KEY = "nss"
URL_KEY = "url"


class IdentifierSchema(BaseSubSchema):
    """Identifier schema."""

    nss = StringField()
    url = StringField()
