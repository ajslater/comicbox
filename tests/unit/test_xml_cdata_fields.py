"""
XML scalar fields read a tag's text even when the tag carries attributes.

xmltodict renders `<Series lang="en">Captain Science</Series>` as
`{"@lang": "en", "#text": "Captain Science"}`. `CDataFieldMixin` exists to
unwrap that `#text`, but every `Xml*` field listed the mixin *after* its value
field, so the MRO reached the value field's `_deserialize` first and the mixin
never ran. Attribute-bearing tags raised, and the clearing error store dropped
them without a trace.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

import pytest
from marshmallow.exceptions import ValidationError

from comicbox.box import Comicbox
from comicbox.enums.comicbox import ReadingDirectionEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields import xml_fields
from comicbox.formats.base.fields.enum_fields import ComicInfoMangaEnum
from comicbox.formats.base.fields.xml_fields import (
    CDataFieldMixin,
    XmlBooleanField,
    XmlComicInfoMangaField,
    XmlDateField,
    XmlDateTimeField,
    XmlDecimalField,
    XmlEnumField,
    XmlIntegerField,
    XmlIssueField,
    XmlLanguageField,
    XmlOriginalFormatField,
    XmlPdfDateTimeField,
    XmlReadingDirectionField,
    XmlStringField,
    XmlYesNoField,
)

if TYPE_CHECKING:
    from marshmallow.fields import Field


class _ColorEnum(Enum):
    """A concrete enum, because XmlEnumField's own ENUM is the empty base."""

    RED = "Red"


class _XmlColorField(XmlEnumField):
    """Instantiable stand-in for XmlEnumField."""

    ENUM = _ColorEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


# One instantiable field and one representative tag text per scalar XML field.
_CASES: dict[type, tuple[Field, str, Any]] = {
    XmlStringField: (XmlStringField(), "Marvel", "Marvel"),
    XmlIssueField: (XmlIssueField(), "#001", "1"),
    XmlDateField: (XmlDateField(), "2020-01-02", date(2020, 1, 2)),
    XmlDateTimeField: (
        XmlDateTimeField(),
        "2020-01-02T03:04:05",
        datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    ),
    XmlPdfDateTimeField: (
        XmlPdfDateTimeField(),
        "2020-01-02T03:04:05",
        datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    ),
    XmlEnumField: (_XmlColorField(), "red", _ColorEnum.RED),
    XmlReadingDirectionField: (
        XmlReadingDirectionField(),
        "ltr",
        ReadingDirectionEnum.LTR,
    ),
    XmlOriginalFormatField: (
        XmlOriginalFormatField(),
        "trade paperback",
        "Trade Paperback",
    ),
    XmlComicInfoMangaField: (
        XmlComicInfoMangaField(),
        "YesAndRightToLeft",
        ComicInfoMangaEnum.YES_RTL,
    ),
    XmlYesNoField: (XmlYesNoField(), "Yes", True),
    XmlBooleanField: (XmlBooleanField(), "true", True),
    XmlIntegerField: (XmlIntegerField(), "12", 12),
    XmlDecimalField: (XmlDecimalField(), "1.5", Decimal("1.5")),
    XmlLanguageField: (XmlLanguageField(), "en", "en"),
}

_XML_SCALAR_FIELDS = frozenset(
    obj
    for obj in vars(xml_fields).values()
    if isinstance(obj, type)
    and issubclass(obj, CDataFieldMixin)
    and obj is not CDataFieldMixin
)

_PARAMS = tuple(
    pytest.param(field, raw, expected, id=cls.__name__)
    for cls, (field, raw, expected) in _CASES.items()
)

_FIELD_PARAMS = tuple(
    pytest.param(field, id=cls.__name__) for cls, (field, _raw, _ok) in _CASES.items()
)

_CLASS_PARAMS = tuple(
    pytest.param(cls, id=cls.__name__)
    for cls in sorted(_XML_SCALAR_FIELDS, key=lambda field_class: field_class.__name__)
)


def test_every_scalar_xml_field_has_a_case() -> None:
    """A new Xml* scalar field must arrive with a round-trip case."""
    assert frozenset(_CASES) == _XML_SCALAR_FIELDS


@pytest.mark.parametrize("field_class", _CLASS_PARAMS)
def test_cdata_mixin_wins_the_mro(field_class: type[CDataFieldMixin]) -> None:
    """
    The mixin's `_deserialize` is the one the field actually resolves to.

    This is the whole contract: the value fields do not call `super()`, so a
    mixin reached second in the MRO is dead code.
    """
    assert field_class._deserialize is CDataFieldMixin._deserialize


@pytest.mark.parametrize(("field", "raw", "expected"), _PARAMS)
def test_bare_tag_text_parses(field: Field, raw: str, expected: Any) -> None:
    """Establish the value each field reads from a plain tag."""
    assert field.deserialize(raw, "tag", {}) == expected


@pytest.mark.parametrize(("field", "raw", "expected"), _PARAMS)
def test_attributed_tag_parses_the_same(field: Field, raw: str, expected: Any) -> None:
    """An attribute on the tag must not change the value comicbox reads."""
    cdata = {"@id": "9", xml_fields.CDATA_KEY: raw}
    assert field.deserialize(cdata, "tag", {}) == expected


@pytest.mark.parametrize("field", _FIELD_PARAMS)
def test_a_mapping_with_no_text_is_refused(field: Field) -> None:
    """
    A structure standing where a scalar belongs must not read as empty.

    Unwrapping a missing `#text` to None would quietly turn a nested tag into
    no value at all. Raising keeps the drop visible in the error store.
    """
    with pytest.raises(ValidationError):
        field.deserialize({"Inner": "Captain Science"}, "tag", {})


def test_a_nested_tag_is_dropped_loudly() -> None:
    """End to end: the bad tag goes, the rest of the file stays."""
    xml = (
        '<?xml version="1.0"?><ComicInfo>'
        "<Series><Inner>Captain Science</Inner></Series>"
        "<Number>1</Number>"
        "</ComicInfo>"
    )
    with Comicbox(metadata=xml, fmt=MetadataFormats.COMIC_INFO) as car:
        md = car.to_dict()["comicbox"]
    assert "series" not in md
    assert md["issue"]["name"] == "1"


def test_attributed_comic_info_tags_survive_a_read() -> None:
    """
    End to end: stray attributes used to take the whole file's metadata down.

    Both tags failed to deserialize, the error store cleared them, and the
    load returned no comicbox metadata at all.
    """
    xml = (
        '<?xml version="1.0"?><ComicInfo>'
        '<Series lang="en">Captain Science</Series>'
        '<Number issue="1">1</Number>'
        "</ComicInfo>"
    )
    with Comicbox(metadata=xml, fmt=MetadataFormats.COMIC_INFO) as car:
        md = car.to_dict()["comicbox"]
    assert md["series"]["name"] == "Captain Science"
    assert md["issue"]["name"] == "1"
