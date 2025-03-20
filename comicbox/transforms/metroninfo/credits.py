"""MetronInfo.xml Transforms for credits."""

from enum import Enum
from types import MappingProxyType

from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    CREDITS_KEY,
    ROLES_KEY,
)
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleAliases, GenericRoleEnum
from comicbox.transforms.credit_role_tag import (
    CreditRoleTagTransformMixin,
    create_role_map,
)
from comicbox.transforms.metroninfo.nested import MetronInfoTransformNestedTags

ROLE_ALIASES: MappingProxyType[Enum, tuple[Enum | str, ...]] = MappingProxyType(
    {
        MetronRoleEnum.ARTIST: (ComicBookInfoRoleEnum.ARTIST,),
        MetronRoleEnum.ASSISTANT_EDITOR: (),
        MetronRoleEnum.ASSOCIATE_EDITOR: (),
        MetronRoleEnum.BREAKDOWNS: (),
        MetronRoleEnum.CHIEF_CREATIVE_OFFICER: (CoMetRoleTagEnum.CREATOR,),
        MetronRoleEnum.COLLECTION_EDITOR: (),
        MetronRoleEnum.COLORIST: (
            GenericRoleEnum.COLOURIST,
            *GenericRoleAliases.COLORIST.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.COLORIST,
            ComicInfoRoleTagEnum.COLORIST,
        ),
        MetronRoleEnum.COLOR_ASSISTS: (),
        MetronRoleEnum.COLOR_FLATS: (),
        MetronRoleEnum.COLOR_SEPARATIONS: (),
        MetronRoleEnum.CONSULTING_EDITOR: (),
        MetronRoleEnum.COVER: (
            *GenericRoleAliases.COVER.value,
            CoMetRoleTagEnum.COVER_DESIGNER,
            ComicInfoRoleTagEnum.COVER_ARTIST,
        ),
        MetronRoleEnum.DESIGNER: (),
        MetronRoleEnum.DIGITAL_ART_TECHNICIAN: (),
        MetronRoleEnum.EDITOR: (
            *GenericRoleAliases.EDITOR.value,
            CoMetRoleTagEnum.EDITOR,
            ComicInfoRoleTagEnum.EDITOR,
        ),
        MetronRoleEnum.EDITOR_IN_CHIEF: (),
        MetronRoleEnum.EMBELLISHER: (),
        MetronRoleEnum.EXECUTIVE_EDITOR: (),
        MetronRoleEnum.EXECUTIVE_PRODUCER: (),
        MetronRoleEnum.FINISHES: (),
        MetronRoleEnum.GRAY_TONE: (),
        MetronRoleEnum.GROUP_EDITOR: (),
        MetronRoleEnum.ILLUSTRATOR: (),
        MetronRoleEnum.INKER: (
            *GenericRoleAliases.INKER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.INKER,
            ComicInfoRoleTagEnum.INKER,
        ),
        MetronRoleEnum.INK_ASSISTS: (),
        MetronRoleEnum.INTERVIEWER: (),
        MetronRoleEnum.LAYOUTS: (),
        MetronRoleEnum.LETTERER: (
            *GenericRoleAliases.LETTERER.value,
            CoMetRoleTagEnum.LETTERER,
            ComicInfoRoleTagEnum.LETTERER,
        ),
        MetronRoleEnum.LOGO_DESIGN: (),
        MetronRoleEnum.MANAGING_EDITOR: (),
        MetronRoleEnum.OTHER: (ComicBookInfoRoleEnum.OTHER,),
        MetronRoleEnum.PENCILLER: (
            *GenericRoleAliases.PENCILLER.value,
            *GenericRoleAliases.PAINTER.value,
            CoMetRoleTagEnum.PENCILLER,
            ComicInfoRoleTagEnum.PENCILLER,
        ),
        MetronRoleEnum.PLOT: (),
        MetronRoleEnum.PRESIDENT: (),
        MetronRoleEnum.PRODUCTION: (),
        MetronRoleEnum.PUBLISHER: (),
        MetronRoleEnum.SCRIPT: (),
        MetronRoleEnum.SENIOR_EDITOR: (),
        MetronRoleEnum.STORY: (),
        MetronRoleEnum.SUPERVISING_EDITOR: (),
        MetronRoleEnum.TRANSLATOR: (
            *GenericRoleAliases.TRANSLATOR.value,
            ComicInfoRoleTagEnum.TRANSLATOR,
        ),
        MetronRoleEnum.WRITER: (
            GenericRoleEnum.AUTHOR,
            *GenericRoleAliases.WRITER.value,
            CoMetRoleTagEnum.WRITER,
            ComicInfoRoleTagEnum.WRITER,
        ),
    }
)


class MetronInfoTransformCredits(
    MetronInfoTransformNestedTags, CreditRoleTagTransformMixin
):
    """MetronInfo.xml Transforms for credits."""

    ROLE_MAP = create_role_map(ROLE_ALIASES)
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
        metron_roles = []
        if metron_role_enums := cls.get_role_enums(role_name):
            # Handle expanding one role into many.
            metron_role = []
            for metron_role_enum in metron_role_enums:
                metron_role = cls._unparse_identified_name(
                    data, metron_role_enum, comicbox_role
                )
                metron_roles.append(metron_role)
        return metron_roles

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
