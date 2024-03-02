"""ComicInfo Pages Transform Mixin."""

from bidict import bidict

from comicbox.dict_funcs import sort_dict
from comicbox.schemas.comicbox_mixin import INDEX_KEY, PAGES_KEY


class ComicInfoPagesTransformMixin:
    """ComicInfo Pages Transform Mixin."""

    PAGES_TAG = "Pages"
    PAGES_SUB_TAG = "Page"
    INDEX_TAG = "@Image"
    PAGE_TRANSFORM = bidict(
        {
            INDEX_TAG: INDEX_KEY,
            "@Type": "page_type",
            "@DoublePage": "double_page",
            "@ImageSize": "size",
            "@Key": "key",
            "@Bookmark": "bookmark",
            "@ImageWidth": "width",
            "@ImageHeight": "height",
        }
    )
    DOUBLE_RESOURCE_TAGS = (PAGES_TAG,)

    def _create_new_pages_list(self, pages_list, to_comicbox):
        new_pages_list = []
        for page in pages_list:
            new_page = self.copy_keys(page, self.PAGE_TRANSFORM, not to_comicbox)  # type: ignore
            new_page = sort_dict(new_page)
            new_pages_list.append(new_page)
        sort_key = INDEX_KEY if to_comicbox else self.INDEX_TAG
        return sorted(new_pages_list, key=lambda p: p.get(sort_key))

    def _pages_copy(self, data, to_comicbox=False):
        """Copy pages keys to other schema."""
        pages_key = self.PAGES_TAG if to_comicbox else PAGES_KEY
        pages_list = data.get(pages_key)
        if pages_list and to_comicbox and self.PAGES_SUB_TAG:
            pages_list = pages_list.get(self.PAGES_SUB_TAG)
        if not pages_list:
            return data
        new_pages_list = self._create_new_pages_list(pages_list, to_comicbox)
        if not to_comicbox and self.PAGES_SUB_TAG:
            new_pages_list = {self.PAGES_SUB_TAG: new_pages_list}
        pages_key = PAGES_KEY if to_comicbox else self.PAGES_TAG
        data[pages_key] = new_pages_list
        return data

    def parse_pages(self, data):
        """Copy pages keys to comicbox schema."""
        return self._pages_copy(data, True)

    def unparse_pages(self, data):
        """Copy pages keys from comicbox schema."""
        return self._pages_copy(data)
