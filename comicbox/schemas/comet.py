"""A class to encapsulate CoMet data."""
# http://www.denvog.com/comet/comet-specification/

from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.xml_fields import (
    XmlDateField,
    XmlDecimalField,
    XmlIntegerField,
    XmlIssueField,
    XmlLanguageField,
    XmlReadingDirectionField,
    XmlStringField,
    XmlStringSetField,
)
from comicbox.schemas.xml_schemas import XmlSchema, XmlSubSchema

IDENTIFIER_TAG = "identifier"
IS_VERSION_OF_TAG = "isVersionOf"


class CoMetRoleTagEnum(Enum):
    """Comet Role tags."""

    COLORIST = "colorist"
    COVER_DESIGNER = "colorDesigner"
    CREATOR = "creator"
    EDITOR = "editor"
    INKER = "inker"
    LETTERER = "letterer"
    PENCILLER = "penciller"
    WRITER = "writer"


class CoMetSubSchema(XmlSubSchema):
    """CoMet Sub Schema."""

    character = XmlStringSetField()
    coverImage = XmlStringField()  # noqa: N815
    date = XmlDateField()
    description = XmlStringField()
    genre = XmlStringSetField()
    identifier = XmlStringSetField(as_string=True)
    isVersionOf = XmlStringSetField(as_string=True)  # noqa: N815
    issue = XmlIssueField()
    language = XmlLanguageField()
    lastMark = XmlIntegerField(minimum=0)  # noqa: N815
    pages = XmlIntegerField(minimum=0)
    publisher = XmlStringField()
    price = XmlDecimalField(minimum=Decimal("0.0"), places=2)
    rating = XmlStringField()
    readingDirection = XmlReadingDirectionField()  # noqa: N815
    rights = XmlStringField()
    series = XmlStringField()
    title = XmlStringField()
    volume = XmlIntegerField(minimum=0)

    # Credit Roles
    colorist = XmlStringSetField()
    coverDesigner = XmlStringSetField()  # noqa: N815
    creator = XmlStringSetField()
    editor = XmlStringSetField()
    inker = XmlStringSetField()
    letterer = XmlStringSetField()
    penciller = XmlStringSetField()
    writer = XmlStringSetField()

    class Meta(XmlSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType(
            {
                "@xmlns:comet": Constant("http://www.denvog.com/comet/"),
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "http://www.denvog.com/comet/comet.xsd"
                ),
                "format": XmlStringField(),
            }
        )


class CoMetSchema(XmlSchema):
    """CoMet Schema."""

    CONFIG_KEYS = frozenset({"comet"})
    FILENAME = "CoMet.xml"
    ROOT_TAGS = ("comet",)

    comet = Nested(CoMetSubSchema)
