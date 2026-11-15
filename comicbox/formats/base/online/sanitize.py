"""
HTML sanitization for description / long-text fields from online sources.

ComicVine's `description` is HTML; mokkari's `desc` may also contain
HTML in some records. We strip all tags and return plain text. The
result is what comicbox stores in `summary` and similar fields.

We use `nh3` (the Python binding to the Rust `ammonia` library — same
maintainers as bleach, much faster). Plain-text output is the v1
choice; downstream tools can render however they like.
"""

from __future__ import annotations

import re
from html import unescape

import nh3

# Block-level tags whose closing should leave a newline in the plain
# text. nh3 strips tags but leaves whitespace as-is; we want
# paragraph breaks preserved.
_BLOCK_RE = re.compile(
    r"</?(?:p|div|br|li|ol|ul|h[1-6]|tr|th|td|hr|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def strip_html(text: str | None) -> str | None:
    """
    Strip all HTML tags, returning plain text with paragraph breaks preserved.

    Block-level tags collapse to single newlines so the result reads
    like text rather than running together. Inline tags drop entirely.
    Runs of three+ newlines collapse to two (paragraph spacing). The
    result is text, not HTML: ``&amp;`` is ``&``.

    Returns None for None input, "" for empty input.
    """
    if text is None:
        return None
    if not text:
        return ""
    # Convert block-level tag positions to newlines before nh3 strips them.
    pre = _BLOCK_RE.sub("\n", text)
    # nh3 returns HTML: it escapes what it keeps, so "&" comes back "&amp;".
    # Unescape after cleaning, so markup spelled as entities stays text.
    cleaned = unescape(nh3.clean(pre, tags=set()))
    return _MULTI_NEWLINE_RE.sub("\n\n", cleaned).strip()
