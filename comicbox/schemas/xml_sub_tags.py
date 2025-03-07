"""Xml Sub Tags like Pages and Metron Resources."""

from types import MappingProxyType

from marshmallow.fields import Field, Nested

from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.schemas.base import BaseSubSchema


def create_sub_tag_field(
    sub_tag: str,
    field: Field,
) -> Nested:
    """Create a nested single schema, common to xml schemas."""
    sub_tag_schema_name = sub_tag + "Schema"
    sub_tag_schema_class = type(sub_tag_schema_name, (BaseSubSchema,), {sub_tag: field})
    return Nested(sub_tag_schema_class)


class XmlPageInfoSchema(BaseSubSchema):
    """ComicPageInfo Structure for ComicInfo.xml."""

    class Meta(BaseSubSchema.Meta):
        """Illegal Field Names."""

        include = MappingProxyType(
            {
                "@Bookmark": StringField(),
                "@DoublePage": BooleanField(),
                "@Key": StringField(),
                "@Image": IntegerField(minimum=0),
                "@ImageWidth": IntegerField(minimum=0),
                "@ImageHeight": IntegerField(minimum=0),
                "@ImageSize": IntegerField(minimum=0),
                "@Type": PageTypeField(),
            }
        )


def create_pages_field():
    """Create pages sub_tag_field."""
    return create_sub_tag_field("Page", Nested(XmlPageInfoSchema, many=True))
