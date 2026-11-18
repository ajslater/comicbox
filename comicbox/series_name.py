"""
Series names, normalized for comparing.

One normalizer for the online matcher, so the name a filename gives and the
name a database gives are compared as the same string.
"""

import re
import unicodedata

# The Combining Diacritical Marks block: the accents on Latin, Greek and
# Cyrillic letters.
_DIACRITICS_START = "̀"
_DIACRITICS_END = "ͯ"
# A volume suffix: "Vol. 2", "(Volume 3)". Without a leading whitespace run,
# which made a long run of spaces quadratic: whitespace is collapsed after.
_VOLUME_SUFFIX_RE = re.compile(
    r"(?:\(\s*)?(?:vol(?:ume|\.)?)\s*\d+\s*\)?", re.IGNORECASE
)


def normalize_series(name: str) -> str:
    """
    Normalize a series name for comparing.

    Latin accents are dropped (``Pokémon`` is ``pokemon``), case is folded,
    a volume suffix is stripped, and every run of characters that are not
    letters or digits, in any script, becomes one space, so ``ワンピース``
    keeps a name. Only the Combining Diacritical Marks block is dropped:
    other combining marks, such as kana voicing (``ピ`` is not ``ヒ``), are
    part of the letter and recompose with it. An ASCII name normalizes as
    lowercase letters and digits with single spaces between them.
    """
    return _spaced(_VOLUME_SUFFIX_RE.sub(" ", _folded(name)))


def _folded(text: str) -> str:
    """Drop Latin accents and fold case, keeping every other mark."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(
        char for char in decomposed if not _DIACRITICS_START <= char <= _DIACRITICS_END
    )
    return unicodedata.normalize("NFC", stripped).casefold()


def _spaced(text: str) -> str:
    """Make every run of characters that are not letters or digits one space."""
    spaced = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(spaced.split())
