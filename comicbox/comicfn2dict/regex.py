"""Parsing regexes."""
import re


def re_compile(exp, parenthify=False):
    """Compile regex with options."""
    if parenthify:
        exp = r"\(" + exp + r"\)"
    return re.compile(exp, flags=re.IGNORECASE)


ORIGINAL_FORMAT_PATTERNS = (
    r"Anthology",
    r"(One|1)[-\s]Shot",
    r"Annual",
    r"Annotation[s]?",
    r"Box[-\s]Set",
    r"Digital",
    r"Director[’']?s\sCut",  # noqa: RUF001
    r"Giant([-\s]Size(d)?)?",
    r"Graphic\sNovel",
    r"Hard[-\s]?Cover",
    r"HC",
    r"HD-Upscaled",
    r"King[-\s]Size(d)?",
    r"Magazine",
    r"Manga?",
    r"Omnibus",
    r"PDF([-\s]Rip)?",
    r"Preview",
    r"Prologue",
    r"Scanlation",
    r"Script",
    r"Sketch",
    r"TPB",
    r"Trade[-\s]Paper[-\s]?Back",
    r"Web([-\s]?Comic)?",
)


# CLEAN
NON_SPACE_DIVIDER_RE = re_compile(r"[_\+]")
DASH_SPLIT_RE = re_compile(r"\s-\s")
EXTRA_SPACES_RE = re_compile(r"\s\s+")

# PAREN GROUPS
ISSUE_COUNT_RE = re_compile(r"of\s*(?P<issue_count>\d+)", parenthify=True)
_YEAR_RE_EXP = r"(?P<year>[12]\d{3})"
YEAR_TOKEN_RE = re_compile(_YEAR_RE_EXP, parenthify=True)
YEAR_BEGIN_RE = re_compile(r"^" + _YEAR_RE_EXP + r"\b")
YEAR_END_RE = re_compile(r"\b" + _YEAR_RE_EXP + r"$")
_OF_PATTERNS = r"|".join(ORIGINAL_FORMAT_PATTERNS)
_ORIGINAL_FORMAT_RE_EXP = r"(?P<original_format>" + _OF_PATTERNS + r")"
ORIGINAL_FORMAT_RE = re_compile(_ORIGINAL_FORMAT_RE_EXP, parenthify=True)
_SCAN_INFO_RE_EXP = r"(?P<scan_info>[^()]+?)"
SCAN_INFO_RE = re_compile(_SCAN_INFO_RE_EXP, parenthify=True)
_ORIGINAL_FORMAT_SCAN_INFO_RE_EXP = (
    _ORIGINAL_FORMAT_RE_EXP + r"(?:-" + _SCAN_INFO_RE_EXP + r")?"
)
ORIGINAL_FORMAT_SCAN_INFO_RE = re_compile(
    _ORIGINAL_FORMAT_SCAN_INFO_RE_EXP, parenthify=True
)

# REGULAR TOKENS
VOLUME_RE = re_compile(r"((?:v(?:ol(?:ume)?)?\.?)\s*(?P<volume>\d+))")
_ISSUE_RE_EXP = r"(?P<issue>[\d½]+\.?\d*\w*)"
ISSUE_NUMBER_RE = re_compile(r"(#" + _ISSUE_RE_EXP + r")")
ISSUE_TOKEN_RE = re_compile(r"^(" + _ISSUE_RE_EXP + r")$")
ISSUE_END_RE = re_compile(r"\b(" + _ISSUE_RE_EXP + r")$")
ISSUE_BEGIN_RE = re_compile(r"^(" + _ISSUE_RE_EXP + r")\b")
ISSUE_ANYWHERE_RE = re_compile(r"\b(" + _ISSUE_RE_EXP + r")\b")

# LONG STRINGS
REMAINING_GROUP_RE = re_compile(r"^[\w].*[^\)]")
