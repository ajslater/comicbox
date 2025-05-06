"""A class to encapsulate CoMet data."""
# http://www.denvog.com/comet/comet-specification/

from decimal import Decimal
from types import MappingProxyType

from marshmallow.fields import Nested

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
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubHeadSchema,
    create_xml_headers,
)

IDENTIFIER_TAG = "identifier"
IS_VERSION_OF_TAG = "isVersionOf"


class CoMetSubSchema(XmlSubHeadSchema):
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

    class Meta(XmlSubHeadSchema.Meta):
        """Schema Options."""

        NS = "comet"
        NS_URI = "http://www.denvog.com/comet/"
        XSD_URI = (
            "https://github.com/ajslater/comicbox/blob/main/schemas/CoMet-v1.1.xsd"
        )

        include = MappingProxyType(
            {
                **create_xml_headers(NS, NS_URI, XSD_URI),
                "format": XmlStringField(),
            }
        )


class CoMetSchema(XmlSchema):
    """CoMet Schema."""

    ROOT_TAG: str = "comet"
    ROOT_KEYPATH: str = ROOT_TAG
    HAS_PAGE_COUNT: bool = True

    comet = Nested(CoMetSubSchema)
