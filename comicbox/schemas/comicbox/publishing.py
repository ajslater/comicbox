"""Comicbox Publishing Schemas."""

from marshmallow.fields import Nested

from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import DecimalField, IntegerField
from comicbox.fields.pycountry import LanguageField
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.comicbox.identifiers import IdentifiedNameSchema, IdentifiedSchema


class SeriesSchema(IdentifiedNameSchema):
    """Series Schema."""

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
    """Schema for Reprints of this issue."""

    language = LanguageField()  # Metron ONLY
    series = Nested(SeriesSchema)  # Comet, CIX, CT
    volume = Nested(VolumeSchema)  # Comet, CIX, CT, Metron
    issue = StringField()  # Comet, CIX, CT, Metron
