"""Author to Credits transforms."""

from comicbox.schemas.comicbox import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.schemas.enums.comet import CoMetRoleTagEnum
from comicbox.schemas.enums.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.enums.metroninfo import MetronRoleEnum
from comicbox.schemas.enums.role import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.spec import MetaSpec

_AUTHOR_VALUES = frozenset(
    {
        enum.value
        for enum in (
            GenericRoleEnum.AUTHOR,
            MetronRoleEnum.WRITER,
            MetronRoleEnum.SCRIPT,
            MetronRoleEnum.STORY,
            MetronRoleEnum.PLOT,
            MetronRoleEnum.TRANSLATOR,
            CoMetRoleTagEnum.CREATOR,
            CoMetRoleTagEnum.WRITER,
            ComicInfoRoleTagEnum.WRITER,
            ComicInfoRoleTagEnum.TRANSLATOR,
        )
    }
    | {*GenericRoleAliases.WRITER.value}
)


def _authors_to_credits(authors):
    return {author: {ROLES_KEY: {"Writer": {}}} for author in authors if author}


def _credits_to_authors(comicbox_credits):
    authors = set()
    for person_name, comicbox_credit in comicbox_credits.items():
        if not person_name:
            continue
        comicbox_roles = comicbox_credit.get(ROLES_KEY, {})
        for role_name in comicbox_roles:
            if role_name.lower() in _AUTHOR_VALUES:
                authors.add(person_name)
    return authors


def authors_to_credits_transform_to_cb(author_tag):
    """Create a Transform for pdf authors to comicbox credits."""
    return MetaSpec(
        key_map={CREDITS_KEY: author_tag},
        spec=_authors_to_credits,
    )


def authors_to_credits_transform_from_cb(author_tag):
    """Create a Transform for pdf authors to comicbox credits."""
    return MetaSpec(
        key_map={author_tag: CREDITS_KEY},
        spec=_credits_to_authors,
    )
