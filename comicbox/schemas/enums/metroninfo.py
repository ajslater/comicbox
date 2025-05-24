"""MetronInfo.xml Enums."""

from enum import Enum

from comicbox.identifiers import (
    ID_SOURCE_NAME_MAP,
    IdSources,
)


class MetronAgeRatingEnum(Enum):
    """Metron Age Rating Types."""

    UNKNOWN = "Unknown"
    EVERYONE = "Everyone"
    TEEN = "Teen"
    TEEN_PLUS = "Teen Plus"
    MATURE = "Mature"
    EXPLICIT = "Explicit"
    ADULT = "Adult"


class GenericFormatEnum(Enum):
    """Generic Format Values."""

    ANTHOLOGY = "Anthology"
    ANNOTATION = "Annotation"
    BOX_SET = "Box Set"
    DIGITAL = "Digital"
    DIRECTORS_CUT = "Directors Cut"
    DIRECTOR_S_CUT = "Director's Cut"
    GIANT_SIZED = "Giant Sized"
    GN = "GN"
    HARD_COVER = "Hard Cover"
    HC = "HC"
    HD_UPSCALED = "HD Upscaled"
    KING_SIZED = "King Sized"
    MAGAZINE = "Magazine"
    MANGA = "Manga"
    ONE_DASH_SHOT = "1-Shot"
    PDF_RIP = "PDF Rip"
    PREVIEW = "Preview"
    PROLOGUE = "Prologue"
    SCANLATION = "Scanlation"
    SCRIPT = "Script"
    TBP = "TPB"
    WEB_COMIC = "Web Comic"
    WEB_RIP = "Web Rip"


class MetronFormatEnum(Enum):
    """Metron Series Format Values."""

    ANNUAL = "Annual"
    DIGITAL_CHAPTER = "Digital Chapter"
    GRAPHIC_NOVEL = "Graphic Novel"
    HARDCOVER = "Hardcover"
    LIMITED_SERIES = "Limited Series"
    OMNIBUS = "Omnibus"
    ONE_SHOT = "One-Shot"
    SINGLE_ISSUE = "Single Issue"
    TRADE_PAPERBACK = "Trade Paperback"


class MetronRoleEnum(Enum):
    """Valid Metron Roles."""

    WRITER = "Writer"
    SCRIPT = "Script"
    STORY = "Story"
    PLOT = "Plot"
    INTERVIEWER = "Interviewer"
    ARTIST = "Artist"
    PENCILLER = "Penciller"
    BREAKDOWNS = "Breakdowns"
    ILLUSTRATOR = "Illustrator"
    LAYOUTS = "Layouts"
    INKER = "Inker"
    EMBELLISHER = "Embellisher"
    FINISHES = "Finishes"
    INK_ASSISTS = "Ink Assists"
    COLORIST = "Colorist"
    COLOR_SEPARATIONS = "Color Separations"
    COLOR_ASSISTS = "Color Assists"
    COLOR_FLATS = "Color Flats"
    DIGITAL_ART_TECHNICIAN = "Digital Art Technician"
    GRAY_TONE = "Gray Tone"
    LETTERER = "Letterer"
    COVER = "Cover"
    EDITOR = "Editor"
    CONSULTING_EDITOR = "Consulting Editor"
    ASSISTANT_EDITOR = "Assistant Editor"
    ASSOCIATE_EDITOR = "Associate Editor"
    GROUP_EDITOR = "Group Editor"
    SENIOR_EDITOR = "Senior Editor"
    MANAGING_EDITOR = "Managing Editor"
    COLLECTION_EDITOR = "Collection Editor"
    PRODUCTION = "Production"
    DESIGNER = "Designer"
    LOGO_DESIGN = "Logo Design"
    TRANSLATOR = "Translator"
    SUPERVISING_EDITOR = "Supervising Editor"
    EXECUTIVE_EDITOR = "Executive Editor"
    EDITOR_IN_CHIEF = "Editor In Chief"
    PRESIDENT = "President"
    PUBLISHER = "Publisher"
    CHIEF_CREATIVE_OFFICER = "Chief Creative Officer"
    EXECUTIVE_PRODUCER = "Executive Producer"
    OTHER = "Other"


class MetronSourceEnum(Enum):
    """Metron Valid Sources."""

    ANILIST = ID_SOURCE_NAME_MAP[IdSources.ANILIST.value]
    COMICVINE = ID_SOURCE_NAME_MAP[IdSources.COMICVINE.value]
    GCD = ID_SOURCE_NAME_MAP[IdSources.GCD.value]
    KITSU = ID_SOURCE_NAME_MAP[IdSources.KITSU.value]
    LCG = ID_SOURCE_NAME_MAP[IdSources.LCG.value]
    MANGADEX = ID_SOURCE_NAME_MAP[IdSources.MANGADEX.value]
    MANGAUPDATES = ID_SOURCE_NAME_MAP[IdSources.MANGAUPDATES.value]
    METRON = ID_SOURCE_NAME_MAP[IdSources.METRON.value]
    MYANIMELIST = ID_SOURCE_NAME_MAP[IdSources.MYANIMELIST.value]
