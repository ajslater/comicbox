"""Metron Community Rating Schema."""

from decimal import Decimal

from comicbox.formats.base.fields.xml_fields import XmlDecimalField, XmlIntegerField
from comicbox.formats.base.schemas.xml_schemas import XmlSubSchema


class MetronCommunityRatingSchema(XmlSubSchema):
    """Metron Community Rating Schema."""

    AverageRating = XmlDecimalField(
        required=True, places=1, minimum=Decimal(0), maximum=Decimal(5)
    )
    RatingCount = XmlIntegerField(minimum=1)
