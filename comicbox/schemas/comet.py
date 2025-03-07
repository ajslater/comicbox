"""A class to encapsulate CoMet data."""

from decimal import Decimal
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

COLORIST_TAG = "colorist"
COVER_DESIGNER_TAG = "coverDesigner"
CREATOR_TAG = "creator"
EDITOR_TAG = "editor"
INKER_TAG = "inker"
LETTERER_TAG = "letterer"
PENCILLER_TAG = "penciller"
WRITER_TAG = "writer"


class CoMetSubSchema(XmlSubSchema):
    """CoMet Sub Schema."""

    # http://www.denvog.com/comet/comet-specification/
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
    price = XmlDecimalField(minimum=Decimal("0.0"))
    rating = XmlStringField()
    readingDirection = XmlReadingDirectionField()  # noqa: N815
    rights = XmlStringField()
    series = XmlStringField()
    title = XmlStringField()
    volume = XmlIntegerField(minimum=0)

    # Contributors
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
