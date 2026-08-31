"""Comicbox Identifier Schemas."""

from marshmallow.fields import Nested

from comicbox.formats.base.fields.collection_fields import DictField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.schemas.base import BaseSubSchema


class IdentifierSchema(BaseSubSchema):  # Comet, CIX, CT, Metron
    """
    One database's id for a thing.

    No url is stored. MetronInfo keeps its IDS and URLs in separate lists and
    comicbox does the same: web links live in the top level ``urls`` verbatim,
    and the url for an identifier is derived from its key on demand. Storing
    both invited them to disagree.

    ``id_type`` names what the key identifies and is only recorded when it
    differs from the type implied by where the identifier sits — every id
    under ``series`` is a series id, so it says nothing. A hand-tagged key
    like ``series:178012`` written at the issue level is the case that needs
    it, since the type decides which url the key builds.
    """

    key = StringField()
    id_type = StringField()


class IdentifiedSchema(BaseSubSchema):  # Metron ONLY
    """Identified Schema."""

    identifiers = DictField(values=Nested(IdentifierSchema))


class IdentifiedNameSchema(IdentifiedSchema):  # Comicbox
    """Named Element with an identifier."""

    name = StringField()
