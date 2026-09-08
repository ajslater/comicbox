"""Identifier consts."""

import re
from collections.abc import Container, Iterator

from comicbox.enums.comicbox import AlternateIdSources, IdSources

# Ordered best source first, because IdSources declares them that way.
ID_SOURCE_VALUES = tuple(id_source.value for id_source in IdSources)
DEFAULT_ID_SOURCE = IdSources.COMICVINE
DEFAULT_ID_TYPE = "issue"

# The GTIN family: sources that are a barcode rather than a database id.
# Ordered by write preference for a format with a single barcode tag: ISBN
# first as the most specific, the generic GTIN last.
BARCODE_ID_SOURCES = (IdSources.ISBN, IdSources.UPC, IdSources.GTIN)

# Field names inside the comicbox identifier dict shape.
ID_KEY_KEY = "key"
ID_TYPE_KEY = "id_type"


def ranked_id_sources(candidates: Container[str]) -> Iterator[str]:
    """Yield the id source values in candidates, best ranked source first."""
    return (
        id_source_str
        for id_source_str in ID_SOURCE_VALUES
        if id_source_str in candidates
    )


_ALTERNATE_ID_SOURCES = tuple(id_source.value for id_source in AlternateIdSources)
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
ID_SOURCE_GROUP = "id_source"
ALT_ID_SOURCE_GROUP = "alt_id_source"
# A source name only names a source when a colon follows it. Without that,
# every tag and genre that merely starts with one, like "marvel-comics",
# minted an identifier for a database that never heard of it. The cvdb and
# cmxdb alternates are the exception: they were coined as bare prefixes.
IDENTIFIER_RE_EXP = (
    r"(?:"
    r"(?P<" + ID_SOURCE_GROUP + r">" + r"|".join(ID_SOURCE_VALUES) + r"):"
    r"|(?P<" + ALT_ID_SOURCE_GROUP + r">" + r"|".join(_ALTERNATE_ID_SOURCES) + r"):?"
    r")"
    r"(?:(?P<id_type>" + r"|".join(ID_TYPE_NAMES) + r"):)?"
    r"(?P<id_key>[\w-]+)"
)
# Every comicvine resource type code is 40xx, so a plain pair of numbers
# like a year range is not one.
COMICVINE_LONG_ID_KEY_EXP = r"(?P<id_type>40\d{2})-(?P<id_key>\d+)"
PARSE_COMICVINE_RE = re.compile(COMICVINE_LONG_ID_KEY_EXP)


def match_id_source_str(match: re.Match) -> str:
    """Get the id source from either of the two source groups."""
    return match.group(ID_SOURCE_GROUP) or match.group(ALT_ID_SOURCE_GROUP) or ""
