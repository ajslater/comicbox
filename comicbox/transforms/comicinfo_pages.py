"""ComicInfo Pages Transform Mixin."""

from collections.abc import Mapping

from comicbox.schemas.comicbox_mixin import PAGE_INDEX_KEY, PAGES_KEY
from comicbox.transforms.transform_map import (
    KeyTransforms,
    create_transform_map,
    transform_map,
)
from comicbox.transforms.xml_transforms import XmlTransform


class ComicInfoPagesTransformMixin(XmlTransform):
    """ComicInfo Pages Transform Mixin."""

    PAGES_TAG = "Pages"
    PAGES_SUB_TAG = "Page"
    INDEX_TAG = "@Image"
    PAGE_TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                INDEX_TAG: PAGE_INDEX_KEY,
                "@Type": "page_type",
                "@DoublePage": "double_page",
                "@ImageSize": "size",
                "@Key": "key",
                "@Bookmark": "bookmark",
                "@ImageWidth": "width",
                "@ImageHeight": "height",
            }
        )
    )
    DOUBLE_RESOURCE_TAGS = (PAGES_TAG,)

    def _pages_copy(
        self,
        data,
        pages_copy_from: str,
        page_transform_map: Mapping,
        pages_copy_to: str,
    ):
        """Copy pages keys to other schema."""
        pages_list = data.pop(pages_copy_from, None)
        if pages_list and self.PAGES_SUB_TAG and pages_copy_from == self.PAGES_TAG:
            # Hoist
            pages_list = pages_list.get(self.PAGES_SUB_TAG)
        if pages_list:
            new_pages_list = [
                transform_map(page_transform_map, page) for page in pages_list
            ]
            if new_pages_list:
                if self.PAGES_SUB_TAG and pages_copy_to == self.PAGES_TAG:
                    # Lower
                    new_pages_list = {self.PAGES_SUB_TAG: new_pages_list}
                data[pages_copy_to] = new_pages_list
        return data

    def parse_pages(self, data):
        """Copy pages keys to comicbox schema."""
        return self._pages_copy(
            data, self.PAGES_TAG, self.PAGE_TRANSFORM_MAP, PAGES_KEY
        )

    def unparse_pages(self, data):
        """Copy pages keys from comicbox schema."""
        return self._pages_copy(
            data, PAGES_KEY, self.PAGE_TRANSFORM_MAP.inverse, self.PAGES_TAG
        )
