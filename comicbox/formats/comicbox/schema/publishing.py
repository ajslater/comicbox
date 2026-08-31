"""Comicbox Publishing Schemas."""

from marshmallow.fields import Nested

from comicbox.formats.base.fields.collection_fields import ListField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import DecimalField, IntegerField
from comicbox.formats.base.fields.pycountry import LanguageField
from comicbox.formats.base.schemas.base import BaseSubSchema
from comicbox.formats.comicbox.schema.identifiers import (
    IdentifiedNameSchema,
    IdentifiedSchema,
)


class AlternativeNameSchema(IdentifiedNameSchema):
    """
    Another name this series goes by.

    MetronInfo's Series/AlternativeNames: translated titles, romanizations
    and variant spellings of the same series. Distinct from a reprint, which
    is a different edition of this issue's content.
    """

    language = LanguageField()  # Metron ONLY


class SeriesSchema(IdentifiedNameSchema):
    """Series Schema."""

    alternative_names = ListField(  # Metron ONLY
        Nested(AlternativeNameSchema), sort_keys=("language", "name")
    )
    sort_name = StringField()  # Metron ONLY
    start_year = IntegerField()  # Metron ONLY
    volume_count = IntegerField(minimum=0)  # CBI, CT, Metron


class VolumeSchema(BaseSubSchema):
    """Volume Schema."""

    issue_count = IntegerField(minimum=0)  # CBI, CT, CIX, Filename, Metron
    number = IntegerField(minimum=0)  # All
    number_to = IntegerField(minimum=0)  # Metron ONLY


class IssueSchema(BaseSubSchema):
    """Issue Schema."""

    name = StringField()  # All
    number = DecimalField()  # Comicbox
    suffix = StringField()  # Comicbox


class ReprintSchema(IdentifiedSchema):
    """
    Another edition of this issue's content.

    ``name`` is what the source said and is what gets written back. The
    structured fields are read out of it for convenience; they are never the
    authority, because a reprint name is free text that no filename grammar
    fully describes.
    """

    name = StringField()  # Metron, Comet
    language = LanguageField()  # Metron ONLY
    series = Nested(SeriesSchema)  # Comet, CIX, CT
    volume = Nested(VolumeSchema)  # Comet, CIX, CT, Metron
    issue = StringField()  # Comet, CIX, CT, Metron
