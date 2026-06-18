"""Page Schema."""

from comicbox.formats.base.fields.enum_fields import PageTypeField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import BooleanField, IntegerField
from comicbox.formats.base.schemas.base import BaseSubSchema


class PageInfoSchema(BaseSubSchema):  # CIX, CT - ONLY
    """Comicbox page info schema."""

    bookmark = StringField()
    double_page = BooleanField()
    key = StringField()
    width = IntegerField(minimum=0)
    height = IntegerField(minimum=0)
    size = IntegerField(minimum=0)
    page_type = PageTypeField()
