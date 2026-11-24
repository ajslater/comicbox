"""ComicRack's reading-list XML, ``.cbl``: read and write."""

from comicbox.readinglists.formats import ReadingListFormat
from comicbox.readinglists.formats.cbl.transform import CblTransform

# No schema exists for the dialect, so validation is a parse and its warnings.
CBL_REGISTRATION = ReadingListFormat(
    label="ComicRack Reading List",
    tokens=frozenset({"cbl"}),
    suffix=".cbl",
    transform_class=CblTransform,
    lexer="xml",
)
