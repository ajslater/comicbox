"""ComicInfo Pages Transformer creator."""

from collections.abc import Mapping

from bidict import frozenbidict

from comicbox.schemas.comicbox_mixin import PAGES_KEY
from comicbox.transforms.transform_map import (
    KeyTransforms,
    transform_map,
)


def _cix_pages_transform(page_transform_map: Mapping, pages: list):
    """Transform a list of pages with the supplied transform map."""
    return [transform_map(page_transform_map, page) for page in pages]


def comicinfo_pages_transform(page_transform_map: frozenbidict):
    """Create a pages transformer with a page transform map."""

    def cix_transform_to_pages(pages: list):
        """Transform pages from comicinfo to comicbox."""
        return _cix_pages_transform(page_transform_map, pages)

    def cix_transform_from_pages(pages: list):
        """Transform pages from comicbox to comicinfo."""
        return _cix_pages_transform(page_transform_map.inverse, pages)

    return KeyTransforms(
        key_map={"Pages.Page": PAGES_KEY},
        to_cb=cix_transform_to_pages,
        from_cb=cix_transform_from_pages,
    )
