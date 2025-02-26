"""MetronInfo.xml Transforms for credits."""

from enum import Enum
from types import MappingProxyType

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.schemas.comicinfo import (
    ComicInfoRoleTagEnum,
)
from comicbox.schemas.metroninfo import (
    MetronRoleEnum,
)
from comicbox.transforms.credit_role_tag import create_role_map
from comicbox.transforms.metroninfo.identifiers import MetronInfoTransformIdentifiers


class MetronInfoTransformCredits(MetronInfoTransformIdentifiers):
    """MetronInfo.xml Transforms for credits."""

    PRE_ROLE_MAP: MappingProxyType[Enum, Enum | tuple[Enum, ...]] = MappingProxyType(
        {
            **{enum: enum for enum in MetronRoleEnum},
            CoMetRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
            CoMetRoleTagEnum.COVER_DESIGNER: MetronRoleEnum.COVER,
            CoMetRoleTagEnum.CREATOR: MetronRoleEnum.CHIEF_CREATIVE_OFFICER,
            CoMetRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
            CoMetRoleTagEnum.INKER: MetronRoleEnum.INKER,
            CoMetRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
            CoMetRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
            ComicInfoRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
            ComicInfoRoleTagEnum.COVER_ARTIST: MetronRoleEnum.COVER,
            ComicInfoRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
            ComicInfoRoleTagEnum.INKER: MetronRoleEnum.INKER,
            ComicInfoRoleTagEnum.LETTERER: MetronRoleEnum.LETTERER,
            ComicInfoRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
            ComicInfoRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
            ComicInfoRoleTagEnum.TRANSLATOR: MetronRoleEnum.TRANSLATOR,
            ComicBookInfoRoleEnum.ARTIST: MetronRoleEnum.ARTIST,
            ComicBookInfoRoleEnum.OTHER: MetronRoleEnum.OTHER,
        }
    )
    ROLE_MAP = create_role_map(PRE_ROLE_MAP)
    CREATOR_TAG = "Creator"

    def _parse_credit(self, data: dict, metron_credit) -> tuple[str, dict]:
        """Copy a single metron style credit entry into comicbox credits."""
        metron_creator = metron_credit.pop(self.CREATOR_TAG, {})
        person_name, comicbox_credit = self._parse_identified_name(
            data, metron_creator, "creator"
        )
        comicbox_credit = self._parse_metron_tag(
            metron_credit,
            self.ROLES_TAG,
            # TODO Don't know how to specify optional args to the Callable type
            self._parse_identified_name,  # type: ignore[reportInvalidTypeForm]
            "role",
            data=data,
        )
        return person_name, comicbox_credit

    def parse_credits(self, data: dict):
        """Copy metron style credits dict into contributors."""
        return self._parse_metron_tag(data, self.CREDITS_TAG, self._parse_credit)

    @classmethod
    def _unparse_role(cls, data, role_name, comicbox_role):
        """Unparse a metron role to an enum only value."""
        if role_name and (metron_role_enum := cls.ROLE_MAP.get(role_name.lower())):
            return cls._unparse_identified_name(data, metron_role_enum, comicbox_role)
        return {}

    @classmethod
    def _unparse_credit(
        cls, data: dict, person_name: str, comicbox_credit: dict
    ) -> dict:
        """Aggregate comicbox credits into Metron credit dict."""
        if not person_name:
            return {}
        metron_creator = cls._unparse_identified_name(
            data, person_name, comicbox_credit
        )
        metron_credit = {cls.CREATOR_TAG: metron_creator}
        metron_roles = cls._unparse_metron_tag(
            comicbox_credit, ROLES_KEY, cls._unparse_role, data=data
        )
        metron_credit.update(metron_roles)
        return metron_credit

    def unparse_credits(self, data):
        """Dump contributors into metron style credits dict."""
        return self._unparse_metron_tag(data, CREDITS_KEY, self._unparse_credit)
