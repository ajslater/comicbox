"""ComicInfo Pages Transformer creator."""

from collections.abc import Mapping

from glom import SKIP, Coalesce, Fill, T, glom
from glom.grouping import Group
from loguru import logger

from comicbox.empty import is_empty
from comicbox.schemas.comicbox import BOOKMARK_KEY, PAGE_INDEX_KEY, PAGES_KEY
from comicbox.schemas.comicinfo import IMAGE_ATTRIBUTE
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

_KEY_SPEC = Coalesce(T[IMAGE_ATTRIBUTE], skip=is_empty, default=SKIP)


def comicinfo_pages_to_cb(pages_key_path: str, page_key_map: Mapping):
    """Transform comicinfo pages into comicbox."""
    page_spec = create_specs_to_comicbox(
        MetaSpec(key_map=page_key_map, inherit_root_keypath=False)
    )
    value_spec = Coalesce(dict(page_spec), skip=is_empty, default=SKIP)
    value_spec = Fill(value_spec)

    return MetaSpec(
        key_map={PAGES_KEY: pages_key_path},
        spec=(Group({_KEY_SPEC: value_spec}),),
    )


def _pages_from_cb(values: Mapping, page_spec: dict):
    cix_pages = []
    comicbox_pages = values.get(PAGES_KEY)
    if not comicbox_pages:
        return cix_pages
    comicbox_bookmark = values.get(BOOKMARK_KEY)
    for index, comicbox_page in comicbox_pages.items():
        try:
            comicbox_page[PAGE_INDEX_KEY] = index
            if index == comicbox_bookmark:
                comicbox_page[BOOKMARK_KEY] = "true"
            if cix_page := glom(comicbox_page, page_spec):
                cix_pages.append(cix_page)
        except Exception as ex:
            reason = f"Error transforming comicbox page to ComicInfo style page: {ex}"
            logger.debug(reason)
    return cix_pages


def comicinfo_pages_from_cb(pages_key_path: str, page_key_map: Mapping):
    """Transform comicbox pages into comicinfo."""
    page_spec = create_specs_from_comicbox(
        MetaSpec(key_map=page_key_map, inherit_root_keypath=False)
    )

    def from_cb(values):
        return _pages_from_cb(values, dict(page_spec))

    return MetaSpec(
        key_map={pages_key_path: (PAGES_KEY, BOOKMARK_KEY)},
        spec=(from_cb,),
    )


def comicinfo_bookmark_to_cb(pages_key_path: str, bookmark_attr: str, image_attr: str):
    """Get the bookmark from pages."""

    def get_bookmark(pages):
        for page in pages:
            if page.get(bookmark_attr):
                return page.get(image_attr)
        return None

    return MetaSpec(key_map={BOOKMARK_KEY: pages_key_path}, spec=(get_bookmark,))
