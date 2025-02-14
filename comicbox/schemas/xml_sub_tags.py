"""Xml Sub Tags like Pages and Metron Resources."""

from marshmallow.fields import Field, Nested

from comicbox.schemas.base import BaseSubSchema


def create_sub_tag_field(
    sub_tag: str,
    field: Field,
) -> Nested:
    """Create a nested single schema, common to xml schemas."""
    sub_tag_schema_name = sub_tag + "Schema"
    sub_tag_schema_class = type(sub_tag_schema_name, (BaseSubSchema,), {sub_tag: field})
    return Nested(sub_tag_schema_class)
