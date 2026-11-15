"""
ComicRack's reading-list XML, ``.cbl``.

The dialect has no published schema. These schemas describe what
ComicRack, Mylar, Kavita, YACReader, Komga and DieselTech's community files
write: attributes on ``<Book>`` and ``<Database>``, any number of
``<Database>`` children, and an empty ``<Matchers />`` that only a smart
list fills. ``<NumIssues>``, ``Book@Format``, ``Book/<Id>`` and
``<FileName>`` are not declared, so they are ignored on read.
"""

import sys
from types import MappingProxyType

from marshmallow.fields import Nested, Raw

from comicbox.formats.base.fields.xml_fields import (
    XmlIntegerField,
    XmlListField,
    XmlStringField,
)
from comicbox.formats.base.schemas.xml_schemas import (
    XmlSchema,
    XmlSubHeadSchema,
    XmlSubSchema,
)

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

READING_LIST_TAG = "ReadingList"
NAME_TAG = "Name"
NUM_ISSUES_TAG = "NumIssues"
START_YEAR_TAG = "StartYear"
SOURCE_TAG = "Source"
BOOKS_TAG = "Books"
BOOK_TAG = "Book"
DATABASE_TAG = "Database"
MATCHERS_TAG = "Matchers"
NAME_ATTR = "@Name"
SERIES_ATTR = "@Series"
NUMBER_ATTR = "@Number"
VOLUME_ATTR = "@Volume"
YEAR_ATTR = "@Year"
ISSUE_ATTR = "@Issue"
_XSD_ATTR = "@xmlns:xsd"
_XSI_ATTR = "@xmlns:xsi"


class CblDatabaseSchema(XmlSubSchema):
    """A database's series and issue ids for a book."""

    TAG_ORDER = (NAME_ATTR, SERIES_ATTR, ISSUE_ATTR)

    class Meta(XmlSubSchema.Meta):
        """XML attributes."""

        include = MappingProxyType(
            {
                NAME_ATTR: XmlStringField(),
                SERIES_ATTR: XmlStringField(),
                ISSUE_ATTR: XmlStringField(),
            }
        )


class CblBookSchema(XmlSubSchema):
    """One issue in the list."""

    TAG_ORDER = (SERIES_ATTR, NUMBER_ATTR, VOLUME_ATTR, YEAR_ATTR, DATABASE_TAG)

    Database = XmlListField(Nested(CblDatabaseSchema), sort=False)

    class Meta(XmlSubSchema.Meta):
        """XML attributes."""

        include = MappingProxyType(
            {
                SERIES_ATTR: XmlStringField(),
                NUMBER_ATTR: XmlStringField(),
                VOLUME_ATTR: XmlStringField(),
                YEAR_ATTR: XmlStringField(),
            }
        )


class CblBooksSchema(XmlSubSchema):
    """The books, in reading order."""

    TAG_ORDER = (BOOK_TAG,)

    Book = XmlListField(Nested(CblBookSchema), sort=False)


class CblSubSchema(XmlSubHeadSchema):
    """The ``<ReadingList>`` element."""

    TAG_ORDER = (
        _XSD_ATTR,
        _XSI_ATTR,
        NAME_TAG,
        NUM_ISSUES_TAG,
        START_YEAR_TAG,
        SOURCE_TAG,
        BOOKS_TAG,
        MATCHERS_TAG,
    )

    Name = XmlStringField()
    NumIssues = XmlIntegerField(minimum=0)
    StartYear = XmlIntegerField()
    Source = XmlStringField()
    Books = Nested(CblBooksSchema)
    # A smart list's rules. Kept raw: only whether it is empty matters.
    Matchers = Raw()

    @override
    @classmethod
    def sort_dump(cls, data: dict) -> dict:
        """Write the empty ``<Matchers />`` ComicRack always writes."""
        data = super().sort_dump(data)
        data[MATCHERS_TAG] = None
        return data


class CblSchema(XmlSchema):
    """A ComicRack reading list."""

    ROOT_TAG = READING_LIST_TAG
    ROOT_KEYPATH = READING_LIST_TAG

    ReadingList = Nested(CblSubSchema)
