"""Unparse comic filenames."""


from typing import Callable


def issue_formatter(issue):
    """Formatter to zero pad issues."""
    i = 0
    issue = issue.lstrip("0")
    for c in issue:
        if not c.isdigit():
            break
        i += 1
    pad = 3 + len(issue) - i
    return "#{:0>" + str(pad) + "}"


_PAREN_FMT = "({})"
_FILENAME_FORMAT_TAGS = (
    ("series", "{}"),
    ("volume", "v{}"),
    ("issue", issue_formatter),
    ("issue_count", "(of {:03})"),
    ("year", _PAREN_FMT),
    ("title", "{}"),
    ("original_format", _PAREN_FMT),
    ("scan_info", _PAREN_FMT),
)
_EMPTY_VALUES = (None, "")


def unparse(md):
    """Get our preferred basename from a metadata dict."""
    if not md:
        return None
    tokens = []
    for tag, fmt in _FILENAME_FORMAT_TAGS:
        val = md.get(tag)
        if val in _EMPTY_VALUES:
            continue
        final_fmt = fmt(val) if isinstance(fmt, Callable) else fmt
        token = final_fmt.format(val).strip()
        if token:
            tokens.append(token)
    fn = " ".join(tokens)
    if remainders := md.get("remainders"):
        remainder = " ".join(remainders)
        fn += f" - {remainder}"
    fn += "." + md.get("ext", "cbz")
    return fn
