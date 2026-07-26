"""Identifier consts."""

import re

from comicbox.enums.comicbox import AlternateIdSources, IdSources

ID_SOURCE_VALUES = (id_source.value for id_source in IdSources)
DEFAULT_ID_SOURCE = IdSources.COMICVINE
DEFAULT_ID_TYPE = "issue"

# Field names inside the comicbox identifier dict shape.
ID_KEY_KEY = "key"
ID_URL_KEY = "url"


_ALL_ID_SOURCES = (
    *ID_SOURCE_VALUES,
    *(id_source.value for id_source in AlternateIdSources),
)
# The public field names of identifiers.IdentifierTypes (drift-guarded by a
# test). Defined here because identifiers.py imports from this module.
ID_TYPE_NAMES = (
    "arc",
    "character",
    "creator",
    "genre",
    "imprint",
    "issue",
    "location",
    "publisher",
    "reprint",
    "role",
    "series",
    "story",
    "tag",
    "team",
    "universe",
    "volume",
)
IDENTIFIER_RE_EXP = (
    r"(?P<id_source>" + r"|".join(_ALL_ID_SOURCES) + r"):?"
    r"(?:(?P<id_type>" + r"|".join(ID_TYPE_NAMES) + r"):)?"
    r"(?P<id_key>[\w-]+)"
)
COMICVINE_LONG_ID_KEY_EXP = r"(?P<id_type>\d{4})-(?P<id_key>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_ID_KEY_EXP)
