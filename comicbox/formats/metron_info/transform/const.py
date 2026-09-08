"""Metron Transform constants."""

from comicbox.enums.comicbox import IdSources

DEFAULT_ID_SOURCE = IdSources.METRON
# MetronInfo's bare `id` attributes and its unsourced ids belong to Metron, the
# database that writes the format. The identifier dicts are keyed by the id
# source *string*, so the fallback has to be the value, not the enum member --
# an enum key here reads back as "IdSources.METRON" and drops out on load.
DEFAULT_ID_SOURCE_STR = DEFAULT_ID_SOURCE.value
