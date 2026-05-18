"""Page Schema."""

from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.schemas.base import BaseSubSchema


class PageInfoSchema(BaseSubSchema):  # CIX, CT - ONLY
    """Comicbox page info schema."""

    bookmark = StringField()
    double_page = BooleanField()
    key = StringField()
    width = IntegerField(minimum=0)
    height = IntegerField(minimum=0)
    size = IntegerField(minimum=0)
    page_type = PageTypeField()
