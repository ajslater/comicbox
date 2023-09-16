"""Page Info Nested Schema."""
from comicbox.fields.enum import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.numbers import BooleanField, IntegerField
from comicbox.schemas.base import BaseSchema

PAGE_TYPE_KEY = "page_type"


class PageInfoSchema(BaseSchema):
    """ComicPageInfo Structure for ComicInfo.xml."""

    index = IntegerField()
    page_type = PageTypeField()
    double_page = BooleanField()
    size = IntegerField()
    key = StringField()
    bookmark = StringField()
    width = IntegerField()
    height = IntegerField()
