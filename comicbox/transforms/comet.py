"""CoMet transforms."""

from types import MappingProxyType

from bidict import bidict
from stringcase import camelcase

from comicbox.schemas.comet import (
    IDENTIFIER_TAG,
    IS_VERSION_OF_TAG,
    CoMetRoleTagEnum,
    CoMetSchema,
)
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    GENRES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
)
from comicbox.schemas.comicinfo import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo import MetronRoleEnum
from comicbox.transforms.comet_reprints import CoMetReprintsTransformMixin
from comicbox.transforms.credit_role_tag import (
    CreditRoleTagTransformMixin,
    create_role_map,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.price_mixin import PriceMixin
from comicbox.transforms.publishing_tags import NestedPublishingTagsMixin
from comicbox.transforms.title_mixin import TitleStoriesMixin
from comicbox.transforms.xml_credits import XmlCreditsTransformMixin
from comicbox.transforms.xml_transforms import XmlTransform


class CoMetTransform(
    XmlTransform,
    XmlCreditsTransformMixin,
    CoMetReprintsTransformMixin,
    NestedPublishingTagsMixin,
    IdentifiersTransformMixin,
    TitleStoriesMixin,
    PriceMixin,
    CreditRoleTagTransformMixin,
):
    """CoMet transforms."""

    TRANSFORM_MAP = bidict(
        {
            "coverImage": "cover_image",
            # "date": "date", handled by code
            "description": SUMMARY_KEY,
            "format": ORIGINAL_FORMAT_KEY,
            # IDENTIFIER_TAG: "identifiers", handled by code
            # "language": LANGUAGE_KEY, handled by code
            "lastMark": "last_mark",
            "pages": PAGE_COUNT_KEY,
            # "publisher": "publisher", handled by code
            # "price": PRICES_KEY coded
            "rating": "age_rating",
            "readingDirection": "reading_direction",
            # "rights": "rights", unused
            # "series": SERIES_KEY,  handled by code
            # "title": "title", handled by code
            # "volume": VOLUME_KEY, handled by code
        }
    )
    STRINGS_TO_NAMED_OBJS_MAP = MappingProxyType(
        {
            "character": CHARACTERS_KEY,
            "genre": GENRES_KEY,
        }
    )
    ROLE_TAGS_ENUM = CoMetRoleTagEnum
    PRE_ROLE_MAP = MappingProxyType(
        {
            **{tag: tag for tag in ROLE_TAGS_ENUM},
            ComicInfoRoleTagEnum.COLORIST: CoMetRoleTagEnum.COLORIST,
            ComicInfoRoleTagEnum.COVER_ARTIST: CoMetRoleTagEnum.COVER_DESIGNER,
            ComicInfoRoleTagEnum.EDITOR: CoMetRoleTagEnum.EDITOR,
            ComicInfoRoleTagEnum.INKER: CoMetRoleTagEnum.INKER,
            ComicInfoRoleTagEnum.PENCILLER: CoMetRoleTagEnum.PENCILLER,
            ComicBookInfoRoleEnum.ARTIST: (
                CoMetRoleTagEnum.WRITER,
                CoMetRoleTagEnum.PENCILLER,
            ),
            # ComicBookInfoRoleEnum.OTHER: CoMetRoleTagEnum.,
            MetronRoleEnum.WRITER: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.SCRIPT: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.STORY: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.PLOT: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.INTERVIEWER: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.ARTIST: (
                CoMetRoleTagEnum.WRITER,
                CoMetRoleTagEnum.PENCILLER,
            ),
            MetronRoleEnum.PENCILLER: CoMetRoleTagEnum.PENCILLER,
            MetronRoleEnum.BREAKDOWNS: CoMetRoleTagEnum.PENCILLER,
            MetronRoleEnum.ILLUSTRATOR: CoMetRoleTagEnum.PENCILLER,
            MetronRoleEnum.LAYOUTS: CoMetRoleTagEnum.PENCILLER,
            MetronRoleEnum.INKER: CoMetRoleTagEnum.INKER,
            MetronRoleEnum.EMBELLISHER: CoMetRoleTagEnum.INKER,
            MetronRoleEnum.FINISHES: CoMetRoleTagEnum.INKER,
            MetronRoleEnum.INK_ASSISTS: CoMetRoleTagEnum.INKER,
            MetronRoleEnum.COLORIST: CoMetRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_SEPARATIONS: CoMetRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_ASSISTS: CoMetRoleTagEnum.COLORIST,
            MetronRoleEnum.COLOR_FLATS: CoMetRoleTagEnum.COLORIST,
            # MetronRoleEnum.DIGITAL_ART_TECHNICIAN: CoMetRoleTagEnum.,
            MetronRoleEnum.GRAY_TONE: CoMetRoleTagEnum.COLORIST,
            MetronRoleEnum.LETTERER: CoMetRoleTagEnum.LETTERER,
            MetronRoleEnum.COVER: CoMetRoleTagEnum.COVER_DESIGNER,
            MetronRoleEnum.EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.CONSULTING_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.ASSISTANT_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.ASSOCIATE_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.GROUP_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.SENIOR_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.MANAGING_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.COLLECTION_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.PRODUCTION: CoMetRoleTagEnum.EDITOR,
            # MetronRoleEnum.DESIGNER: CoMetRoleTagEnum.,
            # MetronRoleEnum.LOGO_DESIGN: CoMetRoleTagEnum.,
            MetronRoleEnum.TRANSLATOR: CoMetRoleTagEnum.WRITER,
            MetronRoleEnum.SUPERVISING_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.EXECUTIVE_EDITOR: CoMetRoleTagEnum.EDITOR,
            MetronRoleEnum.EDITOR_IN_CHIEF: CoMetRoleTagEnum.EDITOR,
            # MetronRoleEnum.PRESIDENT: CoMetRoleTagEnum.,
            # MetronRoleEnum.CHIEF_CREATIVE_OFFICER: CoMetRoleTagEnum.,
            # MetronRoleEnum.EXECUTIVE_PRODUCER: CoMetRoleTagEnum.,
            # MetronRoleEnum.OTHER: CoMetRoleTagEnum.,
        }
    )
    ROLE_MAP = create_role_map(PRE_ROLE_MAP)

    SCHEMA_CLASS = CoMetSchema
    IS_VERSION_OF_TAG = IS_VERSION_OF_TAG
    IDENTIFIERS_TAG = IDENTIFIER_TAG
    NAKED_NID = None
    PUBLISHER_TAG = "publisher"
    SERIES_TAG = "series"
    VOLUME_TAG = "volume"
    ISSUE_COUNT_TAG = ""
    TITLE_TAG = "title"
    PRICE_TAG = "price"

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.parse_credits,
        CoMetReprintsTransformMixin.parse_reprints,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        NestedPublishingTagsMixin.parse_publisher,
        NestedPublishingTagsMixin.parse_series,
        NestedPublishingTagsMixin.parse_volume,
        TitleStoriesMixin.parse_stories,
        PriceMixin.parse_price,
    )
    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        XmlCreditsTransformMixin.unparse_credits,
        CoMetReprintsTransformMixin.unparse_reprints,
        IdentifiersTransformMixin.unparse_identifiers,
        NestedPublishingTagsMixin.unparse_publisher,
        NestedPublishingTagsMixin.unparse_series,
        NestedPublishingTagsMixin.unparse_volume,
        TitleStoriesMixin.unparse_stories,
        PriceMixin.unparse_price,
    )

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return camelcase(data)
